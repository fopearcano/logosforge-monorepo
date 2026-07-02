"""Series scene/episode Reflection — the Counterpart/Logos mirror (Phase 4).

A deterministic, non-mutating reflection for a Series *Scene* (its ordered
teleplay blocks) and *Episode* (a Chapter's scenes). It re-projects the Phase 3
diagnostics (scene + episode), the Phase 2 Season/Arc + Episode Beat plans, PSYKE,
and the Timeline into a writer-facing report seen through five episodic lenses —

* **Audience** — what plays for the viewer: hook, legible conflict & emotional
  progression, exposition load, and whether the cliffhanger / reveal / act break /
  tag lands and leaves a reason to keep watching.
* **Showrunner** — does the scene serve the episode and the episode the season:
  A/B/C balance, setup/payoff & serialized threads, escalation vs. repetition.
* **Character Arc** — per character: want, change, reveal-through-action, and
  consistency with PSYKE (conservative; never creates PSYKE entries).
* **Episode Structure** — cold open / act breaks / climax / tag / sequence and
  alignment with the Episode Beat Plan.
* **Writers-Room** — practical, writer-facing notes and the showrunner note
  (cut / combine / escalate / clarify / move).

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

from logosforge import series_blocks as sbk
from logosforge import series_diagnostics as sd

# Reuse the Phase 3 severity scale (single source of truth).
SEV_INFO = sd.SEV_INFO
SEV_WATCH = sd.SEV_WATCH
SEV_WEAK = sd.SEV_WEAK
SEV_CRITICAL = sd.SEV_CRITICAL

# Section keys (also the canonical render order).
SEC_SNAPSHOT = "Scene Snapshot"
SEC_AUDIENCE = "Audience Perspective"
SEC_SHOWRUNNER = "Showrunner Perspective"
SEC_CHARACTER = "Character Arc Perspective"
SEC_EPISODE = "Episode Structure Perspective"
SEC_WRITERS = "Writers-Room Notes"
SEC_DIALOGUE = "Dialogue / Action Notes"
SEC_ABC = "A/B/C Story Alignment"
SEC_SEASON = "Season / Arc Alignment"
SEC_BEAT = "Beat Plan Alignment"
SEC_TIMELINE = "Timeline / Continuity Risks"
SEC_PSYKE = "PSYKE / Continuity Risks"
SEC_QUESTIONS = "Revision Questions"
SEC_ACTIONS = "Suggested Human Actions"

EXPOSITION_WORDS = 60          # one character's total dialogue words ~ talky
REDUNDANCY_JACCARD = 0.5       # body overlap with the previous scene ~ repetitive


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _content_words(text: str) -> set[str]:
    return sd._content_words(text)


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
    thread: str = ""
    psyke_entry_id: int | None = None
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "title": self.title, "detail": self.detail,
                "severity": self.severity, "block_number": self.block_number,
                "thread": self.thread, "psyke_entry_id": self.psyke_entry_id,
                "suggested_action": self.suggested_action}


@dataclass
class CharacterReflection:
    name: str
    linked: bool = False
    psyke_entry_id: int | None = None
    wants: str = "unclear"
    arc_movement: str = "unclear"      # unclear | present
    dialogue_function: str = "—"
    notes: list[str] = field(default_factory=list)
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "linked": self.linked,
                "psyke_entry_id": self.psyke_entry_id, "wants": self.wants,
                "arc_movement": self.arc_movement,
                "dialogue_function": self.dialogue_function,
                "notes": list(self.notes), "suggestion": self.suggestion}


@dataclass
class SeriesReflectionReport:
    scene_id: int | None = None
    chapter: str = ""
    episode_label: str = ""
    snapshot: str = ""
    audience: list[ReflectionItem] = field(default_factory=list)
    showrunner: list[ReflectionItem] = field(default_factory=list)
    character_arc: list[CharacterReflection] = field(default_factory=list)
    episode_structure: list[ReflectionItem] = field(default_factory=list)
    writers_room: list[ReflectionItem] = field(default_factory=list)
    dialogue_notes: list[ReflectionItem] = field(default_factory=list)
    abc_alignment: list[ReflectionItem] = field(default_factory=list)
    season_alignment: list[ReflectionItem] = field(default_factory=list)
    beat_alignment: list[ReflectionItem] = field(default_factory=list)
    timeline_risks: list[ReflectionItem] = field(default_factory=list)
    continuity_risks: list[ReflectionItem] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    ai_enhanced: bool = False

    def _item_sections(self):
        return (
            (SEC_AUDIENCE, self.audience), (SEC_SHOWRUNNER, self.showrunner),
            (SEC_EPISODE, self.episode_structure), (SEC_WRITERS, self.writers_room),
            (SEC_DIALOGUE, self.dialogue_notes), (SEC_ABC, self.abc_alignment),
            (SEC_SEASON, self.season_alignment), (SEC_BEAT, self.beat_alignment),
            (SEC_TIMELINE, self.timeline_risks), (SEC_PSYKE, self.continuity_risks),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "scene_id": self.scene_id, "chapter": self.chapter,
            "episode_label": self.episode_label, "snapshot": self.snapshot,
            SEC_CHARACTER: [c.to_dict() for c in self.character_arc]}
        for header, items in self._item_sections():
            out[header] = [i.to_dict() for i in items]
        out["questions"] = list(self.questions)
        out["suggested_actions"] = list(self.suggested_actions)
        out["metrics"] = dict(self.metrics)
        out["ai_enhanced"] = self.ai_enhanced
        return out

    def to_text(self) -> str:
        lines: list[str] = [f"{SEC_SNAPSHOT}: {self.snapshot}", ""]
        lines.append(SEC_AUDIENCE + ":")
        lines.extend(f"- [{i.severity}] {i.title} — {i.detail}" for i in self.audience) \
            if self.audience else lines.append("- Nothing flagged.")

        lines.append("")
        lines.append(SEC_SHOWRUNNER + ":")
        if self.showrunner:
            for i in self.showrunner:
                lines.append(f"- [{i.severity}] {i.title} — {i.detail}")
        else:
            lines.append("- Nothing flagged.")

        lines.append("")
        lines.append(SEC_CHARACTER + ":")
        if self.character_arc:
            for c in self.character_arc:
                tag = "" if c.linked else " (unlinked)"
                lines.append(f"- {c.name}{tag} — wants: {c.wants}; arc: "
                             f"{c.arc_movement}; dialogue: {c.dialogue_function}")
                if c.suggestion:
                    lines.append(f"    → {c.suggestion}")
        else:
            lines.append("- No speaking characters detected.")

        for header, items in self._item_sections():
            if header in (SEC_AUDIENCE, SEC_SHOWRUNNER):
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

    def section_text(self, header: str) -> str:
        """Render a single named section (for per-perspective Logos actions)."""
        if header == SEC_CHARACTER:
            if not self.character_arc:
                return f"{header}:\n- No speaking characters detected."
            out = [f"{header}:"]
            for c in self.character_arc:
                tag = "" if c.linked else " (unlinked)"
                out.append(f"- {c.name}{tag} — wants: {c.wants}; arc: "
                           f"{c.arc_movement}; dialogue: {c.dialogue_function}")
                if c.suggestion:
                    out.append(f"    → {c.suggestion}")
            return "\n".join(out)
        items = dict(self._item_sections()).get(header, [])
        if not items:
            return f"{header}:\n- Nothing flagged."
        return f"{header}:\n" + "\n".join(
            f"- [{i.severity}] {i.title} — {i.detail}" for i in items)


# ===========================================================================
# Re-projection helpers
# ===========================================================================


def _to_item(issue: sd.SeriesIssue, category: str,
             psyke_id: int | None = None) -> ReflectionItem:
    return ReflectionItem(category=category, title=issue.label, detail=issue.evidence,
                          severity=issue.severity, block_number=issue.block_number,
                          thread=issue.thread, psyke_entry_id=psyke_id,
                          suggested_action=issue.suggested_action)


def _dialogue_by_character(script: sbk.SeriesScript) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current: str | None = None
    for b in script.blocks:
        if b.block_type == sbk.BT_CHARACTER:
            current = re.sub(r"\(.*?\)", "", b.text).strip().upper()
        elif b.block_type == sbk.BT_DIALOGUE and current:
            out.setdefault(current, []).append(b.text)
        elif b.block_type != sbk.BT_PARENTHETICAL:
            current = None
    return out


def _character_reflections(script: sbk.SeriesScript, diag: sd.SeriesSceneReport,
                           psyke: dict[str, dict]) -> list[CharacterReflection]:
    dialogue_by = _dialogue_by_character(script)
    body = sbk.serialize_series_script(script).lower()
    has_turn = sd._has_any(body, sd.TURN_MARKERS)
    out: list[CharacterReflection] = []
    for name in sbk.character_cues(script):
        entry = psyke.get(name)
        lines = dialogue_by.get(name, [])
        joined = " ".join(lines).lower()
        words = _words(" ".join(lines))
        has_obj = sd._has_any(joined, sd.OBJECTIVE_MARKERS)
        if has_obj:
            wants = "stated in dialogue (verify it's also dramatized)"
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
        arc_movement = "present" if has_turn else "unclear"
        notes: list[str] = []
        if entry is None:
            notes.append("unlinked character — no PSYKE entry")
        if wants == "unclear":
            notes.append("episode-level want unclear")
        if arc_movement == "unclear":
            notes.append("no visible change for this character in the scene")
        suggestion = (
            f"Clarify what {name} wants and what changes for them."
            if wants == "unclear" or arc_movement == "unclear"
            else f"Check {name}'s choice is consistent with their PSYKE arc.")
        out.append(CharacterReflection(
            name=name, linked=entry is not None,
            psyke_entry_id=(entry or {}).get("id"), wants=wants,
            arc_movement=arc_movement, dialogue_function=dialogue_function,
            notes=notes, suggestion=suggestion))
    return out


def _audience_items(script: sbk.SeriesScript,
                    diag: sd.SeriesSceneReport) -> list[ReflectionItem]:
    items: list[ReflectionItem] = []
    ids = {i.id for i in diag.issues}

    if "objective_unclear" in ids or "no_abc_connection" in ids \
            or "no_visible_action" in ids:
        items.append(ReflectionItem(
            category=SEC_AUDIENCE, title="Immediate conflict / hook may be unclear",
            detail="The audience may grasp the premise but not what's at stake right "
                   "now.", severity=SEV_WATCH,
            suggested_action="Make the present want and obstacle clear early."))
    if "dialogue_heavy" in ids or "exposition_heavy" in ids:
        items.append(ReflectionItem(
            category=SEC_AUDIENCE, title="Leans on exposition over action",
            detail="The scene tells more than it shows.", severity=SEV_WATCH,
            suggested_action="Turn a line of exposition into a visible action."))
    if "turn_unclear" in ids and diag.metrics.total_blocks >= 2:
        items.append(ReflectionItem(
            category=SEC_AUDIENCE, title="Scene ends without a new question",
            detail="No reversal or fresh question to pull the viewer forward.",
            severity=SEV_INFO,
            suggested_action="End on a turn, reveal, or unanswered question."))
    # Serial punctuation present but possibly disconnected.
    if (diag.metrics.act_break_count or diag.metrics.teaser_count
            or diag.metrics.tag_count) and "turn_unclear" in ids:
        items.append(ReflectionItem(
            category=SEC_AUDIENCE, title="Serial punctuation may not land",
            detail="A cold open / act break / tag is present but the scene shows no "
                   "clear turn for it to punctuate.", severity=SEV_INFO,
            suggested_action="Tie the marker to a real reveal or decision."))
    return items


def _previous_scene_in_episode(db, project_id: int, chapter: str, scene_id: int):
    try:
        from logosforge import story_structure as ss
        scenes = ss.list_scenes(db, project_id, chapter=chapter)
    except Exception:
        return None
    ids = [s.id for s in scenes]
    if scene_id in ids:
        idx = ids.index(scene_id)
        if idx > 0:
            return scenes[idx - 1]
    return None


def _showrunner_items(db, project_id: int, scene_id: int, chapter: str,
                      body_words: set[str], diag: sd.SeriesSceneReport,
                      ep: sd.SeriesEpisodeReport | None) -> list[ReflectionItem]:
    items: list[ReflectionItem] = []
    ids = {i.id for i in diag.issues}
    if "not_advance_objective" in ids or "unrelated_to_summary" in ids:
        items.append(ReflectionItem(
            category=SEC_SHOWRUNNER, title="Scene's job in the episode is unclear",
            detail="The scene doesn't clearly serve the episode objective / its "
                   "Outline intent.", severity=SEV_WATCH,
            suggested_action="State what this scene must accomplish, or cut/combine it."))
    if "no_abc_connection" in ids:
        items.append(ReflectionItem(
            category=SEC_SHOWRUNNER, title="Scene not tied to an A/B/C story",
            detail="The scene doesn't echo any planned storyline.", severity=SEV_WATCH,
            suggested_action="Assign the scene to a storyline, or update the plan."))
    # Redundancy / escalation vs. the previous scene in the episode.
    prev = _previous_scene_in_episode(db, project_id, chapter, scene_id)
    if prev is not None and body_words:
        prev_words = _content_words(
            sbk.serialize_series_script(sbk.load_scene_script(db, prev.id)))
        if prev_words:
            jac = len(prev_words & body_words) / len(prev_words | body_words)
            if jac >= REDUNDANCY_JACCARD and "turn_unclear" in ids:
                items.append(ReflectionItem(
                    category=SEC_SHOWRUNNER,
                    title="May repeat the previous scene without escalation",
                    detail="This scene strongly overlaps the previous one and shows "
                           "no clear new turn.", severity=SEV_WATCH,
                    suggested_action="Escalate, combine, or cut the redundant beat."))
    if ep is not None:
        for issue in ep.issues_in(sd.CAT_SERIAL):
            if issue.id in ("abc_weak", "abc_none"):
                items.append(_to_item(issue, SEC_SHOWRUNNER))
    return items


# ===========================================================================
# Snapshot + core builder
# ===========================================================================


def _snapshot(scene, diag: sd.SeriesSceneReport, episode_label: str,
              has_episode_plan: bool, has_season_plan: bool) -> str:
    m = diag.metrics
    where = " / ".join(p for p in ((getattr(scene, "act", "") or "").strip(),
                                   episode_label) if p)
    bits = [
        f"{where or 'Unplaced'} · {m.total_blocks} block(s) "
        f"({m.character_count} character / {m.dialogue_count} dialogue / "
        f"{m.action_count} action)",
        f"dialogue:action ratio {m.dialogue_action_ratio}",
    ]
    if has_episode_plan:
        bits.append("episode plan: present")
    if has_season_plan:
        bits.append("season plan: present")
    return " · ".join(bits)


def _questions(diag: sd.SeriesSceneReport,
               ep: sd.SeriesEpisodeReport | None) -> list[str]:
    qs: list[str] = ["What is this scene's job in the episode?"]
    ids = {i.id for i in diag.issues}
    if "objective_unclear" in ids or "not_advance_objective" in ids:
        qs.append("What does each character actively want right now?")
    if "no_abc_connection" in ids:
        qs.append("Which storyline (A/B/C) does this scene advance?")
    if "turn_unclear" in ids:
        qs.append("What changes between the beginning and the end of the scene?")
    if "no_visible_action" in ids or "dialogue_heavy" in ids:
        qs.append("Which line or action makes the audience want the next scene?")
    if ep is not None and any(i.id == "act_break_expected_missing"
                              for i in ep.issues):
        qs.append("Where does this episode earn its act break?")
    qs.append("Showrunner note — cut, combine, escalate, clarify, or move?")
    return list(dict.fromkeys(qs))


def _writers_room(diag: sd.SeriesSceneReport, ep: sd.SeriesEpisodeReport | None,
                  showrunner: list[ReflectionItem]) -> list[ReflectionItem]:
    notes: list[ReflectionItem] = []
    notes.append(ReflectionItem(
        category=SEC_WRITERS, title="What is this scene doing?",
        detail="Name the scene's single job; if you can't, it may need to be cut or "
               "combined.", severity=SEV_INFO))
    if any(i.title.startswith("May repeat") for i in showrunner):
        notes.append(ReflectionItem(
            category=SEC_WRITERS, title="Redundant with the previous scene?",
            detail="Find the beat that escalates, or merge the two scenes.",
            severity=SEV_WATCH))
    if any(i.id == "no_abc_connection" for i in diag.issues):
        notes.append(ReflectionItem(
            category=SEC_WRITERS, title="Can it serve A-story and character arc at once?",
            detail="The strongest series scenes braid plot and character.",
            severity=SEV_INFO))
    notes.append(ReflectionItem(
        category=SEC_WRITERS, title="Showrunner note",
        detail="Decide the one move: cut, combine, escalate, clarify, or move.",
        severity=SEV_INFO))
    return notes


def _collect_actions(report: SeriesReflectionReport,
                     diag: sd.SeriesSceneReport) -> list[str]:
    out: list[str] = []
    for issue in diag.issues:
        if issue.suggested_action:
            out.append(issue.suggested_action)
    for _, items in report._item_sections():
        for it in items:
            if it.suggested_action:
                out.append(it.suggested_action)
    for c in report.character_arc:
        if c.suggestion:
            out.append(c.suggestion)
    return list(dict.fromkeys(out))[:12]


def build_scene_reflection(db, project_id: int, scene_id: int
                           ) -> SeriesReflectionReport:
    """Build a deterministic multi-perspective reflection for a Series scene.
    Read-only — never mutates, never calls the LLM."""
    rep = SeriesReflectionReport(scene_id=scene_id)
    scene = None
    try:
        scene = db.get_scene_by_id(scene_id)
    except Exception:
        scene = None
    if scene is None:
        rep.snapshot = "Scene not found."
        return rep

    script = sbk.load_scene_script(db, scene_id)
    diag = sd.analyze_scene_by_id(db, project_id, scene_id)
    grouped = sd.group_issues_by_category(diag)
    chapter = (getattr(scene, "chapter", "") or "").strip()
    rep.chapter = chapter
    rep.episode_label = sbk.episode_label(chapter) if chapter else ""
    body_words = _content_words(sbk.serialize_series_script(script))

    ep = None
    if chapter:
        try:
            ep = sd.analyze_episode(db, project_id, chapter)
        except Exception:
            ep = None

    psyke: dict[str, dict] = {}
    try:
        from logosforge.screenplay_reflection import _psyke_characters_by_name
        psyke = _psyke_characters_by_name(db, project_id)
    except Exception:
        psyke = {}

    rep.metrics = diag.metrics.to_dict()
    rep.snapshot = _snapshot(scene, diag, rep.episode_label,
                             bool(ep and ep.has_episode_plan),
                             bool(ep and ep.has_season_plan))

    rep.audience = _audience_items(script, diag)
    rep.showrunner = _showrunner_items(db, project_id, scene_id, chapter,
                                       body_words, diag, ep)
    rep.character_arc = _character_reflections(script, diag, psyke)
    rep.episode_structure = ([_to_item(i, SEC_EPISODE)
                              for i in (ep.issues_in(sd.CAT_EPISODE) if ep else [])])
    rep.dialogue_notes = [_to_item(i, SEC_DIALOGUE)
                          for i in grouped.get(sd.CAT_BALANCE, [])]
    rep.dialogue_notes += [_to_item(i, SEC_DIALOGUE)
                           for i in grouped.get(sd.CAT_FORMAT, [])
                           if i.id.startswith(("dialogue_no_character",
                                               "character_no_dialogue"))]
    # A/B/C: scene connection + episode coverage.
    rep.abc_alignment = [_to_item(i, SEC_ABC) for i in diag.issues
                         if i.id == "no_abc_connection"]
    if ep is not None:
        rep.abc_alignment += [_to_item(i, SEC_ABC) for i in ep.issues
                              if i.id in ("abc_weak", "abc_none")]
    rep.season_alignment = ([_to_item(i, SEC_SEASON) for i in ep.issues
                             if i.id in ("no_season_plan", "arc_question_unsupported",
                                         "setup_payoff_unsupported",
                                         "cliffhanger_unsupported", "motif_undeveloped")]
                            if ep else [])
    rep.beat_alignment = _beat_alignment(grouped, ep)
    rep.timeline_risks = _timeline_items(db, project_id, scene_id, ep)
    rep.continuity_risks = _continuity_items(grouped, psyke)
    rep.showrunner += []  # (already populated)
    rep.writers_room = _writers_room(diag, ep, rep.showrunner)
    rep.questions = _questions(diag, ep)
    rep.suggested_actions = _collect_actions(rep, diag)
    return rep


def _beat_alignment(grouped, ep: sd.SeriesEpisodeReport | None) -> list[ReflectionItem]:
    items = [_to_item(i, SEC_BEAT) for i in grouped.get(sd.CAT_ALIGNMENT, [])]
    if ep is not None and not ep.has_episode_plan:
        items.append(ReflectionItem(
            category=SEC_BEAT, title="No Episode beat plan",
            detail="No Episode beat plan to compare against — generate one to reflect "
                   "on alignment.", severity=SEV_INFO))
    elif not items:
        items.append(ReflectionItem(
            category=SEC_BEAT, title="Body broadly reflects the plan",
            detail="No plan/body mismatch detected (keyword check).",
            severity=SEV_INFO))
    return items


def _timeline_items(db, project_id: int, scene_id: int,
                    ep: sd.SeriesEpisodeReport | None) -> list[ReflectionItem]:
    items: list[ReflectionItem] = []
    try:
        events = db.get_timeline_event_ids(project_id) or set()
    except Exception:
        events = set()
    if scene_id in events:
        items.append(ReflectionItem(
            category=SEC_TIMELINE, title="Linked to the Timeline",
            detail="This scene is an explicit Timeline event — keep chronology "
                   "consistent across episodes.", severity=SEV_INFO))
    if ep is not None:
        items += [_to_item(i, SEC_TIMELINE) for i in ep.issues
                  if i.id == "timeline_order_mismatch"]
    return items


def _continuity_items(grouped, psyke: dict[str, dict]) -> list[ReflectionItem]:
    name_to_id = {n: v.get("id") for n, v in psyke.items()}
    items: list[ReflectionItem] = []
    for issue in grouped.get(sd.CAT_CONTINUITY, []):
        cue = issue.id.replace("character_not_in_psyke_", "")
        items.append(_to_item(issue, SEC_PSYKE, psyke_id=name_to_id.get(cue)))
    return items


# ===========================================================================
# Episode-level reflection (Chapter context)
# ===========================================================================


def build_episode_reflection(db, project_id: int, chapter: str
                             ) -> SeriesReflectionReport:
    """Build a deterministic Episode-level reflection (showrunner + episode
    structure + A/B/C + season-arc). Read-only."""
    rep = SeriesReflectionReport(chapter=chapter,
                                 episode_label=sbk.episode_label(chapter))
    try:
        ep = sd.analyze_episode(db, project_id, chapter)
    except Exception as exc:
        rep.snapshot = f"Episode reflection unavailable: {exc}"
        return rep
    rep.snapshot = ep.summary
    rep.metrics = {"scene_count": ep.scene_count,
                   "body_scene_count": ep.body_scene_count,
                   "has_episode_plan": ep.has_episode_plan,
                   "has_season_plan": ep.has_season_plan}
    rep.episode_structure = [_to_item(i, SEC_EPISODE) for i in ep.issues_in(sd.CAT_EPISODE)]
    rep.showrunner = [_to_item(i, SEC_SHOWRUNNER) for i in ep.issues
                      if i.id in ("abc_weak", "abc_none")]
    rep.abc_alignment = [_to_item(i, SEC_ABC) for i in ep.issues
                         if i.id in ("abc_weak", "abc_none")]
    rep.season_alignment = [_to_item(i, SEC_SEASON) for i in ep.issues_in(sd.CAT_SERIAL)
                            if i.id not in ("abc_weak", "abc_none")]
    rep.timeline_risks = [_to_item(i, SEC_TIMELINE) for i in ep.issues
                          if i.id == "timeline_order_mismatch"]
    rep.writers_room = [ReflectionItem(
        category=SEC_WRITERS, title="Does the episode escalate scene to scene?",
        detail="Check each scene raises the stakes or turns the story.",
        severity=SEV_INFO)]
    rep.questions = ["Does every scene serve the episode's spine?",
                     "Where does the episode turn, and where does it land?",
                     "Showrunner note — cut, combine, escalate, clarify, or move?"]
    rep.suggested_actions = list(dict.fromkeys(
        i.suggested_action for i in ep.issues if i.suggested_action))[:12]
    return rep


# ===========================================================================
# AI seam (optional) — grounds the existing Counterpart prompt in the report
# ===========================================================================


def build_reflection_messages(report: SeriesReflectionReport, *,
                              scene_context: str = "") -> list[dict]:
    """Build messages for an optional AI pass that *explains/expands* the
    deterministic reflection. Reuses the existing Counterpart system prompt; the AI
    never rewrites the scene. Deterministic to build (no LLM call here)."""
    from logosforge.counterpart import SYSTEM_PROMPT
    parts: list[str] = []
    if scene_context:
        parts.append(scene_context)
        parts.append("")
    parts.append("Deterministic Series reflection (ground your feedback in this; do "
                 "not rewrite the scene):")
    parts.append(report.to_text())
    parts.append("")
    parts.append("As COUNTERPART, deepen this from the audience's, the showrunner's, "
                 "the character's, and the episode-structure point of view. Point to "
                 "the most important gaps and ask 2-3 sharper questions. Keep it "
                 "structured. Do not produce replacement script.")
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(parts)}]


# ===========================================================================
# Optional: save the reflection as a scene-linked Note (requires confirmation)
# ===========================================================================


def save_reflection_as_note(db, project_id: int, scene_id: int,
                            report: SeriesReflectionReport, *,
                            confirmed: bool = False) -> dict:
    """Save a reflection as a Note linked to the scene. **Requires
    ``confirmed=True``** — nothing is written otherwise. Never auto-saves."""
    if not confirmed:
        return {"ok": False,
                "error": "Saving a reflection note requires confirmation."}
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"ok": False, "error": "Scene not found."}
    title = f"Series Reflection — {(getattr(scene, 'title', '') or 'Scene').strip()}"
    try:
        note = db.create_note(project_id, title, report.to_text(), tags="reflection")
        note_id = getattr(note, "id", note)
        db.link_note_to_scene(note_id, scene_id)
    except Exception as exc:
        return {"ok": False, "error": f"Could not save note: {exc}"}
    return {"ok": True, "note_id": note_id, "scene_id": scene_id}
