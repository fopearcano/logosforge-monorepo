"""Series / teleplay planning pipeline (Phase 2).

The deterministic, safety-critical bridge for episodic writing:

    Outline Act / Episode / Scene summaries
        -> Season / Arc Plan        (act-bound planning artifact)
        -> Episode Beat Plan        (chapter/episode-bound planning artifact)
        -> Series scene draft preview
        -> validated Series script blocks
        -> confirmed apply to the Manuscript Scene body

Design contract (non-negotiable), mirroring ``stage_script_pipeline`` /
``screenplay_pipeline`` / ``graphic_novel_pipeline``:

* The AI **never** overwrites the Manuscript body. Generation only ever produces
  a *Season/Arc plan*, an *Episode beat plan*, or a *scene draft preview*;
  nothing reaches ``Scene.content`` until the author confirms and the change
  passes through Controlled Apply.
* The **Season/Arc plan** and **Episode beat plan** are planning artifacts,
  stored separately from the Manuscript body (``Scene.content``) and from the
  Outline summaries — in project settings (``series_season_plans`` keyed by Act
  name, ``series_episode_plans`` keyed by Chapter/Episode name). **No schema
  change, no Season/Episode storage hierarchy.** This mirrors how the Outline
  already stores ``act_summaries`` / ``chapter_summaries`` (also name-keyed),
  because Acts/Chapters are scene-derived string labels, not tables.
* Apply reuses the existing Controlled Apply gate (``target_type="scene"`` ->
  ``Scene.content``), so the draft lands on the body only via the validated
  Series adapter, after a checkpoint, and only with ``confirmed=True``.

Pure logic: no Qt, no provider/LLM client. Prompt builders return strings; the
parsers turn an LLM reply into structured data; validation is rule-based; the UI
owns the actual provider call and the confirm dialogs. No image generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from logosforge import series_blocks as sbk
from logosforge import story_structure as ss

# Project-settings keys. Season/Arc plans are keyed by Act NAME; Episode beat
# plans are keyed by Chapter/Episode NAME (Acts/Chapters are scene-derived
# labels, never ids — see story_structure). No schema change.
SEASON_KEY = "series_season_plans"
EPISODE_KEY = "series_episode_plans"

# Apply-mode tokens (UI-level intents) — mirror the other pipelines.
APPLY_TO_EMPTY = "apply_to_empty"
APPLY_REPLACE = "replace"
APPLY_APPEND = "append"
APPLY_CANCEL = "cancel"
APPLY_MODES = (APPLY_TO_EMPTY, APPLY_REPLACE, APPLY_APPEND, APPLY_CANCEL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_list(items) -> list[str]:
    return [str(x).strip() for x in (items or []) if str(x).strip()]


# ===========================================================================
# Season / Arc Plan model  (act-bound)
# ===========================================================================


@dataclass
class SeasonArcPlan:
    """A Season / Arc plan for an Act group — separate from body and Outline.

    Bound to an Act by name (``act``), because Acts are scene-derived labels with
    no id. Stored in project settings, project-scoped."""

    act: str = ""
    premise: str = ""
    arc_question: str = ""
    episode_progression: list[str] = field(default_factory=list)
    character_arcs: list[str] = field(default_factory=list)
    recurring_motifs: list[str] = field(default_factory=list)
    setup_payoff_notes: str = ""
    cliffhanger_reveal_notes: str = ""
    continuity_notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def is_empty(self) -> bool:
        return not any((
            self.premise.strip(), self.arc_question.strip(),
            self.setup_payoff_notes.strip(), self.cliffhanger_reveal_notes.strip(),
            self.continuity_notes.strip(), _clean_list(self.episode_progression),
            _clean_list(self.character_arcs), _clean_list(self.recurring_motifs)))

    def to_dict(self) -> dict[str, Any]:
        return {"act": self.act, "premise": self.premise,
                "arc_question": self.arc_question,
                "episode_progression": list(self.episode_progression),
                "character_arcs": list(self.character_arcs),
                "recurring_motifs": list(self.recurring_motifs),
                "setup_payoff_notes": self.setup_payoff_notes,
                "cliffhanger_reveal_notes": self.cliffhanger_reveal_notes,
                "continuity_notes": self.continuity_notes,
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "SeasonArcPlan":
        d = d or {}
        return cls(
            act=d.get("act", "") or "", premise=d.get("premise", "") or "",
            arc_question=d.get("arc_question", "") or "",
            episode_progression=[str(x) for x in (d.get("episode_progression") or [])],
            character_arcs=[str(x) for x in (d.get("character_arcs") or [])],
            recurring_motifs=[str(x) for x in (d.get("recurring_motifs") or [])],
            setup_payoff_notes=d.get("setup_payoff_notes", "") or "",
            cliffhanger_reveal_notes=d.get("cliffhanger_reveal_notes", "") or "",
            continuity_notes=d.get("continuity_notes", "") or "",
            created_at=d.get("created_at", "") or "",
            updated_at=d.get("updated_at", "") or "")

    def to_text(self) -> str:
        lines: list[str] = []
        for label, val in (("Premise", self.premise),
                           ("Arc Question", self.arc_question),
                           ("Setup / Payoff", self.setup_payoff_notes),
                           ("Cliffhangers / Reveals", self.cliffhanger_reveal_notes),
                           ("Continuity Notes", self.continuity_notes)):
            if val.strip():
                lines.append(f"{label}: {val.strip()}")
        for label, items in (("Episode Progression", self.episode_progression),
                             ("Character Arcs", self.character_arcs),
                             ("Recurring Motifs", self.recurring_motifs)):
            its = _clean_list(items)
            if its:
                lines.append(f"{label}:")
                lines.extend(f"- {i}" for i in its)
        return "\n".join(lines)


# ===========================================================================
# Episode Beat Plan model  (chapter / episode-bound)
# ===========================================================================


@dataclass
class EpisodeBeatPlan:
    """An Episode beat plan for a Chapter (displayed as Episode) — planning data,
    never Manuscript body. Bound to a Chapter by name (``chapter``)."""

    chapter: str = ""
    episode_premise: str = ""
    episode_objective: str = ""
    dramatic_question: str = ""
    a_story: str = ""
    b_story: str = ""
    c_story: str = ""
    teaser_or_cold_open: str = ""
    act_breaks: list[str] = field(default_factory=list)
    major_turning_points: list[str] = field(default_factory=list)
    climax: str = ""
    tag_or_button: str = ""
    character_arc_beats: list[str] = field(default_factory=list)
    continuity_notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def is_empty(self) -> bool:
        return not any((
            self.episode_premise.strip(), self.episode_objective.strip(),
            self.dramatic_question.strip(), self.a_story.strip(),
            self.b_story.strip(), self.c_story.strip(),
            self.teaser_or_cold_open.strip(), self.climax.strip(),
            self.tag_or_button.strip(), self.continuity_notes.strip(),
            _clean_list(self.act_breaks), _clean_list(self.major_turning_points),
            _clean_list(self.character_arc_beats)))

    def to_dict(self) -> dict[str, Any]:
        return {"chapter": self.chapter,
                "episode_premise": self.episode_premise,
                "episode_objective": self.episode_objective,
                "dramatic_question": self.dramatic_question,
                "a_story": self.a_story, "b_story": self.b_story,
                "c_story": self.c_story,
                "teaser_or_cold_open": self.teaser_or_cold_open,
                "act_breaks": list(self.act_breaks),
                "major_turning_points": list(self.major_turning_points),
                "climax": self.climax, "tag_or_button": self.tag_or_button,
                "character_arc_beats": list(self.character_arc_beats),
                "continuity_notes": self.continuity_notes,
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "EpisodeBeatPlan":
        d = d or {}
        return cls(
            chapter=d.get("chapter", "") or "",
            episode_premise=d.get("episode_premise", "") or "",
            episode_objective=d.get("episode_objective", "") or "",
            dramatic_question=d.get("dramatic_question", "") or "",
            a_story=d.get("a_story", "") or "", b_story=d.get("b_story", "") or "",
            c_story=d.get("c_story", "") or "",
            teaser_or_cold_open=d.get("teaser_or_cold_open", "") or "",
            act_breaks=[str(x) for x in (d.get("act_breaks") or [])],
            major_turning_points=[str(x) for x in (d.get("major_turning_points") or [])],
            climax=d.get("climax", "") or "",
            tag_or_button=d.get("tag_or_button", "") or "",
            character_arc_beats=[str(x) for x in (d.get("character_arc_beats") or [])],
            continuity_notes=d.get("continuity_notes", "") or "",
            created_at=d.get("created_at", "") or "",
            updated_at=d.get("updated_at", "") or "")

    def has_abc(self) -> dict[str, bool]:
        return {"A": bool(self.a_story.strip()), "B": bool(self.b_story.strip()),
                "C": bool(self.c_story.strip())}

    def to_text(self) -> str:
        lines: list[str] = []
        for label, val in (("Premise", self.episode_premise),
                           ("Objective", self.episode_objective),
                           ("Dramatic Question", self.dramatic_question),
                           ("A Story", self.a_story), ("B Story", self.b_story),
                           ("C Story", self.c_story),
                           ("Teaser / Cold Open", self.teaser_or_cold_open),
                           ("Climax", self.climax), ("Tag / Button", self.tag_or_button),
                           ("Continuity Notes", self.continuity_notes)):
            if val.strip():
                lines.append(f"{label}: {val.strip()}")
        for label, items in (("Act Breaks", self.act_breaks),
                             ("Turning Points", self.major_turning_points),
                             ("Character Arc Beats", self.character_arc_beats)):
            its = _clean_list(items)
            if its:
                lines.append(f"{label}:")
                lines.extend(f"- {i}" for i in its)
        return "\n".join(lines)


# ===========================================================================
# Settings-backed storage (project-bound; name-keyed) — no schema change
# ===========================================================================


def _read(db, project_id: int, key: str) -> dict:
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        return {}
    store = settings.get(key)
    return dict(store) if isinstance(store, dict) else {}


def _write(db, project_id: int, key: str, store: dict) -> None:
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        settings = {}
    settings[key] = store
    db.save_project_settings(project_id, settings)


# -- Season / Arc plan (act-keyed) ------------------------------------------


def get_season_plan(db, project_id: int, act: str) -> SeasonArcPlan | None:
    raw = _read(db, project_id, SEASON_KEY).get(act)
    if not isinstance(raw, dict):
        return None
    plan = SeasonArcPlan.from_dict(raw)
    plan.act = act
    return plan


def has_season_plan(db, project_id: int, act: str) -> bool:
    plan = get_season_plan(db, project_id, act)
    return plan is not None and not plan.is_empty()


def save_season_plan(db, project_id: int, plan: SeasonArcPlan) -> SeasonArcPlan:
    if not (plan.act or "").strip():
        raise ValueError("save_season_plan requires an act name")
    store = _read(db, project_id, SEASON_KEY)
    existing = store.get(plan.act)
    if isinstance(existing, dict) and existing.get("created_at"):
        plan.created_at = existing["created_at"]
    elif not plan.created_at:
        plan.created_at = _now()
    plan.updated_at = _now()
    store[plan.act] = plan.to_dict()
    _write(db, project_id, SEASON_KEY, store)
    return plan


def clear_season_plan(db, project_id: int, act: str) -> bool:
    store = _read(db, project_id, SEASON_KEY)
    if act in store:
        del store[act]
        _write(db, project_id, SEASON_KEY, store)
        return True
    return False


# -- Episode beat plan (chapter-keyed) --------------------------------------


def get_episode_plan(db, project_id: int, chapter: str) -> EpisodeBeatPlan | None:
    raw = _read(db, project_id, EPISODE_KEY).get(chapter)
    if not isinstance(raw, dict):
        return None
    plan = EpisodeBeatPlan.from_dict(raw)
    plan.chapter = chapter
    return plan


def has_episode_plan(db, project_id: int, chapter: str) -> bool:
    plan = get_episode_plan(db, project_id, chapter)
    return plan is not None and not plan.is_empty()


def save_episode_plan(db, project_id: int, plan: EpisodeBeatPlan) -> EpisodeBeatPlan:
    if not (plan.chapter or "").strip():
        raise ValueError("save_episode_plan requires a chapter name")
    store = _read(db, project_id, EPISODE_KEY)
    existing = store.get(plan.chapter)
    if isinstance(existing, dict) and existing.get("created_at"):
        plan.created_at = existing["created_at"]
    elif not plan.created_at:
        plan.created_at = _now()
    plan.updated_at = _now()
    store[plan.chapter] = plan.to_dict()
    _write(db, project_id, EPISODE_KEY, store)
    return plan


def clear_episode_plan(db, project_id: int, chapter: str) -> bool:
    store = _read(db, project_id, EPISODE_KEY)
    if chapter in store:
        del store[chapter]
        _write(db, project_id, EPISODE_KEY, store)
        return True
    return False


# ===========================================================================
# Outline input readers (Act/Chapter/Scene summaries) — read-only
# ===========================================================================


def _act_summary(db, project_id: int, act: str) -> str:
    try:
        raw = (db.get_project_settings(project_id) or {}).get("act_summaries", {})
    except Exception:
        raw = {}
    return str((raw or {}).get(act, "") or "").strip()


def _chapter_summary(db, project_id: int, chapter: str) -> str:
    try:
        raw = (db.get_project_settings(project_id) or {}).get("chapter_summaries", {})
    except Exception:
        raw = {}
    return str((raw or {}).get(chapter, "") or "").strip()


def _episodes_in_act(db, project_id: int, act: str) -> list[tuple[str, str]]:
    """Ordered ``(chapter_name, chapter_summary)`` for the episodes in an Act."""
    out: list[tuple[str, str]] = []
    try:
        tree = ss.build_structure_tree(db, project_id)
    except Exception:
        return out
    for act_name, chapters in tree:
        if act_name != act:
            continue
        for ch_name, _scenes in chapters:
            if ch_name == ss.UNASSIGNED_CHAPTER:
                continue
            out.append((ch_name, _chapter_summary(db, project_id, ch_name)))
    return out


def _act_for_chapter(db, project_id: int, chapter: str) -> str:
    try:
        tree = ss.build_structure_tree(db, project_id)
    except Exception:
        return ""
    for act_name, chapters in tree:
        for ch_name, _scenes in chapters:
            if ch_name == chapter:
                return act_name
    return ""


def _scenes_in_chapter(db, project_id: int, chapter: str) -> list:
    try:
        return ss.list_scenes(db, project_id, chapter=chapter)
    except Exception:
        return []


def _scene_meta(db, scene_id: int) -> dict[str, str]:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"title": "", "summary": "", "act": "", "chapter": ""}
    return {"title": (getattr(scene, "title", "") or "").strip(),
            "summary": (getattr(scene, "summary", "") or "").strip(),
            "act": (getattr(scene, "act", "") or "").strip(),
            "chapter": (getattr(scene, "chapter", "") or "").strip()}


def _mode_block(db, project_id: int) -> str:
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id, mode_context_block)
        return mode_context_block(get_project_writing_mode_by_id(db, project_id))
    except Exception:
        return ""


# ===========================================================================
# Prompt builders
# ===========================================================================

_SEASON_SYSTEM = (
    "You are a series showrunner. Produce a concise SEASON / ARC PLAN — the "
    "serialized spine across episodes — not script and not episode beats. Output "
    "only the labelled plan."
)
_EPISODE_SYSTEM = (
    "You are a TV story editor. Produce a concise EPISODE BEAT PLAN — the dramatic "
    "structure of one episode (teaser, A/B/C stories, act breaks, climax, tag) — "
    "not finished script. Output only the labelled plan."
)
_DRAFT_SYSTEM = (
    "You are a screenwriter for episodic television. Write a teleplay SCENE "
    "realizing ONLY the supplied episode beat plan and scene intent. Output script "
    "only, using teleplay lines: scene headings (INT./EXT.), action, CHARACTER cues "
    "in caps, dialogue, (parentheticals), transitions (CUT TO:), and serial markers "
    "on their own line (COLD OPEN, ACT BREAK, TAG). No markdown, no code fences, no "
    "commentary, and do not restate the plan. No image prompts."
)


def build_season_plan_prompt(db, project_id: int, act: str) -> str:
    parts = ["Create a SEASON / ARC PLAN for this Act / Season group, based on its "
             "intent and the episodes within it — not on any drafted script. Be "
             "concrete and concise."]
    project = db.get_project_by_id(project_id)
    if getattr(project, "title", ""):
        parts.append(f"Project: {project.title}")
    parts.append(f"Act / Season: {act}")
    summary = _act_summary(db, project_id, act)
    if summary:
        parts.append(f"Act / Season summary (intent):\n\"\"\"\n{summary}\n\"\"\"")
    episodes = _episodes_in_act(db, project_id, act)
    if episodes:
        lines = []
        for i, (name, summ) in enumerate(episodes, start=1):
            label = sbk.episode_label(name)
            lines.append(f"- {label} ({name}): {summ}" if summ
                         else f"- {label} ({name})")
        parts.append("Episodes in order:\n" + "\n".join(lines))
    existing = get_season_plan(db, project_id, act)
    if existing is not None and not existing.is_empty():
        parts.append("Existing Season / Arc plan to refine:\n" + existing.to_text())
    mode = _mode_block(db, project_id)
    if mode:
        parts.append(mode)
    parts.append(
        "Respond with ONLY this labelled format (omit a line if not applicable):\n"
        "Premise: <...>\nArc Question: <...>\nEpisode Progression:\n- <ep beat>\n"
        "Character Arcs:\n- <who: arc>\nRecurring Motifs:\n- <motif>\n"
        "Setup / Payoff: <...>\nCliffhangers / Reveals: <...>\n"
        "Continuity Notes: <...>")
    return "\n\n".join(parts)


def build_episode_plan_prompt(db, project_id: int, chapter: str) -> str:
    parts = ["Create an EPISODE BEAT PLAN for this Episode, based on its intent and "
             "its scenes — not on any drafted script. Be concrete and concise."]
    parts.append(f"Episode: {sbk.episode_label(chapter)} ({chapter})")
    summary = _chapter_summary(db, project_id, chapter)
    if summary:
        parts.append(f"Episode summary (intent):\n\"\"\"\n{summary}\n\"\"\"")
    act = _act_for_chapter(db, project_id, chapter)
    if act:
        season = get_season_plan(db, project_id, act)
        if season is not None and not season.is_empty():
            parts.append("Parent Season / Arc plan:\n" + season.to_text())
    scenes = _scenes_in_chapter(db, project_id, chapter)
    if scenes:
        lines = []
        for s in scenes:
            title = (getattr(s, "title", "") or "Untitled").strip()
            summ = (getattr(s, "summary", "") or "").strip()
            lines.append(f"- {title}: {summ}" if summ else f"- {title}")
        parts.append("Scenes in order:\n" + "\n".join(lines))
    existing = get_episode_plan(db, project_id, chapter)
    if existing is not None and not existing.is_empty():
        parts.append("Existing Episode beat plan to refine:\n" + existing.to_text())
    mode = _mode_block(db, project_id)
    if mode:
        parts.append(mode)
    parts.append(
        "Respond with ONLY this labelled format (omit a line if not applicable):\n"
        "Premise: <...>\nObjective: <...>\nDramatic Question: <...>\n"
        "A Story: <...>\nB Story: <...>\nC Story: <...>\n"
        "Teaser / Cold Open: <...>\nAct Breaks:\n- <break>\n"
        "Turning Points:\n- <turn>\nClimax: <...>\nTag / Button: <...>\n"
        "Character Arc Beats:\n- <who: beat>\nContinuity Notes: <...>")
    return "\n\n".join(parts)


def build_draft_prompt(db, project_id: int, scene_id: int,
                       episode: EpisodeBeatPlan | None = None) -> str:
    meta = _scene_meta(db, scene_id)
    ep = episode or (get_episode_plan(db, project_id, meta["chapter"])
                     if meta["chapter"] else None)
    parts = ["Write the teleplay SCENE for this Series scene, realizing ONLY the "
             "episode beat plan and scene intent. Script only — no commentary, no "
             "markdown."]
    if meta["chapter"]:
        parts.append(f"Episode: {sbk.episode_label(meta['chapter'])}")
    if meta["title"]:
        parts.append(f"Scene title: {meta['title']}")
    if ep is not None and not ep.is_empty():
        parts.append("Episode beat plan:\n" + ep.to_text())
    if meta["summary"]:
        parts.append(f"Scene summary:\n\"\"\"\n{meta['summary']}\n\"\"\"")
    existing = sbk.load_scene_script(db, scene_id)
    if not existing.is_empty():
        parts.append("There is existing scene script; the writer will choose to "
                     "replace or append. Write a complete scene draft.")
    parts.append(
        "Use teleplay format on their own lines:\nINT./EXT. LOCATION - TIME\n\n"
        "Action paragraph.\n\nCHARACTER\n(parenthetical)\nDialogue line.\n\n"
        "CUT TO:\n\nSerial markers on their own line when needed: COLD OPEN, "
        "ACT BREAK, TAG.")
    return "\n\n".join(parts)


def season_plan_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _SEASON_SYSTEM},
            {"role": "user", "content": prompt}]


def episode_plan_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _EPISODE_SYSTEM},
            {"role": "user", "content": prompt}]


def draft_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _DRAFT_SYSTEM},
            {"role": "user", "content": prompt}]


# ===========================================================================
# Parsers
# ===========================================================================

_FENCE_RE = re.compile(r"^\s*```[\w-]*\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")


def _strip_fences(text: str) -> str:
    if "```" not in (text or ""):
        return text or ""
    lines = (text or "").splitlines()
    idx = [i for i, ln in enumerate(lines) if _FENCE_RE.match(ln)]
    if len(idx) >= 2:
        return "\n".join(lines[idx[0] + 1:idx[1]])
    return "\n".join(ln for ln in lines if not _FENCE_RE.match(ln))


_SEASON_SINGLE = (
    (("premise",), "premise"),
    (("arc question", "question"), "arc_question"),
    (("setup / payoff", "setup/payoff", "setup payoff", "setup"), "setup_payoff_notes"),
    (("cliffhangers / reveals", "cliffhangers", "reveals", "cliffhanger"),
     "cliffhanger_reveal_notes"),
    (("continuity notes", "continuity"), "continuity_notes"),
)
_SEASON_LIST = {
    "episode progression": "episode_progression", "progression": "episode_progression",
    "character arcs": "character_arcs", "arcs": "character_arcs",
    "recurring motifs": "recurring_motifs", "motifs": "recurring_motifs",
}


def parse_season_plan_response(text: str, act: str = "") -> SeasonArcPlan:
    plan = SeasonArcPlan(act=act)
    cur_list: str | None = None
    for raw in _strip_fences(text or "").splitlines():
        line = raw.rstrip()
        if ":" in line and not _BULLET_RE.match(line):
            head, _, val = line.partition(":")
            key = head.strip().lower()
            single = next((f for labels, f in _SEASON_SINGLE if key in labels), None)
            if single:
                setattr(plan, single, val.strip())
                cur_list = None
                continue
            if key in _SEASON_LIST:
                cur_list = _SEASON_LIST[key]
                if val.strip():
                    getattr(plan, cur_list).append(val.strip())
                continue
        bullet = _BULLET_RE.match(line)
        if cur_list and bullet:
            getattr(plan, cur_list).append(bullet.group(1).strip())
        elif cur_list and line.strip():
            getattr(plan, cur_list).append(line.strip())
    return plan


_EPISODE_SINGLE = (
    (("premise", "episode premise"), "episode_premise"),
    (("objective", "episode objective"), "episode_objective"),
    (("dramatic question", "question"), "dramatic_question"),
    (("a story", "a-story"), "a_story"),
    (("b story", "b-story"), "b_story"),
    (("c story", "c-story"), "c_story"),
    (("teaser / cold open", "teaser", "cold open"), "teaser_or_cold_open"),
    (("climax",), "climax"),
    (("tag / button", "tag", "button"), "tag_or_button"),
    (("continuity notes", "continuity"), "continuity_notes"),
)
_EPISODE_LIST = {
    "act breaks": "act_breaks", "act break": "act_breaks",
    "turning points": "major_turning_points", "turning point": "major_turning_points",
    "major turning points": "major_turning_points",
    "character arc beats": "character_arc_beats", "arc beats": "character_arc_beats",
}


def parse_episode_plan_response(text: str, chapter: str = "") -> EpisodeBeatPlan:
    plan = EpisodeBeatPlan(chapter=chapter)
    cur_list: str | None = None
    for raw in _strip_fences(text or "").splitlines():
        line = raw.rstrip()
        if ":" in line and not _BULLET_RE.match(line):
            head, _, val = line.partition(":")
            key = head.strip().lower()
            single = next((f for labels, f in _EPISODE_SINGLE if key in labels), None)
            if single:
                setattr(plan, single, val.strip())
                cur_list = None
                continue
            if key in _EPISODE_LIST:
                cur_list = _EPISODE_LIST[key]
                if val.strip():
                    getattr(plan, cur_list).append(val.strip())
                continue
        bullet = _BULLET_RE.match(line)
        if cur_list and bullet:
            getattr(plan, cur_list).append(bullet.group(1).strip())
        elif cur_list and line.strip():
            getattr(plan, cur_list).append(line.strip())
    return plan


def parse_draft_response(text: str, scene_id: int | None = None) -> sbk.SeriesScript:
    """Parse a teleplay draft reply into a SeriesScript (strips fences; reuses the
    Phase 1 scene-body parser)."""
    script = sbk.parse_series_text(_strip_fences(text or ""))
    if scene_id is not None:
        for b in script.blocks:
            b.scene_id = scene_id
    return script


# ===========================================================================
# Validation (draft -> errors block, warnings allow). No LLM.
# ===========================================================================

_LEAK_PHRASES = (
    "as an ai", "as a language model", "i cannot ", "i can't ",
    "here is the script", "here's the script", "here is the scene",
    "sure, here", "sure! here", "[series script]", "[series plan]",
    "[episode beat plan]", "[season", "[project mode]", "system prompt",
)
_PLAN_LABELS_IN_BODY = ("premise:", "objective:", "dramatic question:", "a story:",
                        "b story:", "c story:", "arc question:", "act breaks:",
                        "episode progression:")
# Block types whose body text must not be empty in a draft.
_REQUIRE_TEXT = (sbk.BT_SCENE_HEADING, sbk.BT_ACTION, sbk.BT_CHARACTER,
                 sbk.BT_DIALOGUE, sbk.BT_PARENTHETICAL, sbk.BT_TRANSITION,
                 sbk.BT_SHOT)


@dataclass
class DraftValidation:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"is_valid": self.is_valid, "errors": list(self.errors),
                "warnings": list(self.warnings)}


def validate_draft_series_script(
        script: sbk.SeriesScript, *,
        episode: EpisodeBeatPlan | None = None) -> DraftValidation:
    """Rule-based check of a parsed Series draft. Errors block; warnings allow.

    Errors guard the body from junk (empty, leaked fences/commentary, leaked plan
    labels, corrupt/empty required blocks). Structural quirks (no heading,
    dialogue without character, act-break placement) are warnings, plus optional
    A/B/C-coverage warnings when an episode plan expects them."""
    report = DraftValidation()
    if script is None or script.is_empty():
        report.errors.append("The draft has no Series blocks.")
        report.is_valid = False
        return report

    # Corrupt / required-text-missing blocks block the apply.
    for i, b in enumerate(script.blocks):
        if b.block_type not in sbk._VALID:
            report.errors.append(f"Block {i + 1} has an unknown type "
                                 f"({b.block_type!r}).")
        elif b.block_type in _REQUIRE_TEXT and not (b.text or "").strip():
            report.errors.append(f"Block {i + 1} ({b.block_type}) has no text.")

    body = sbk.serialize_series_script(script)
    low = body.lower()
    if "```" in body:
        report.errors.append("The draft contains markdown code fences.")
    if any(p in low for p in _LEAK_PHRASES):
        report.errors.append("The draft contains assistant commentary or leaked context.")
    for b in script.blocks:
        first = (b.text or "").strip().lower().split("\n", 1)[0]
        if b.block_type == sbk.BT_ACTION and any(
                first.startswith(lbl) for lbl in _PLAN_LABELS_IN_BODY):
            report.errors.append("The draft contains the plan instead of Series script.")
            break

    # Structural warnings from the Phase 1 validator (advisory, never block here).
    sv = sbk.validate_series_script(script)
    report.warnings.extend(w for w in sv.warnings if "no script" not in w.lower())

    # Serial-marker placement (draft-specific, advisory): a Tag belongs after the
    # scene body, a Teaser / Cold Open belongs before it.
    first_body = next((i for i, b in enumerate(script.blocks)
                       if b.block_type in (sbk.BT_SCENE_HEADING, sbk.BT_ACTION)), None)
    for i, b in enumerate(script.blocks):
        if b.block_type == sbk.BT_TAG and (first_body is None or i < first_body):
            report.warnings.append("Tag marker appears before the main scene body.")
        elif (b.block_type == sbk.BT_TEASER and first_body is not None
                and i > first_body):
            report.warnings.append("Teaser / Cold Open marker appears after the scene "
                                   "has already started.")

    # Optional A/B/C coverage: if the episode plan expects multiple stories, a very
    # short single-thread draft is worth flagging (advisory only).
    if episode is not None:
        abc = [k for k, v in episode.has_abc().items() if v]
        if len(abc) >= 2 and len(script.blocks) < 4:
            report.warnings.append(
                f"Episode plan defines {'/'.join(abc)} stories but the draft is very "
                "short — it may not serve every storyline.")

    report.errors = list(dict.fromkeys(report.errors))
    report.warnings = list(dict.fromkeys(report.warnings))
    report.is_valid = not report.errors
    return report


# ===========================================================================
# Controlled apply (preview -> confirmed apply)
# ===========================================================================


def _scene_body(db, scene_id: int) -> str:
    scene = db.get_scene_by_id(scene_id)
    return (getattr(scene, "content", "") or "") if scene is not None else ""


def resolve_apply_mode(db, project_id: int, scene_id: int,
                       requested: str) -> tuple[str, bool, str]:
    """Map a UI apply intent to a body-composition decision.

    Returns ``(effective_mode, requires_extra_confirm, error)``. ``apply_to_empty``
    is refused on a non-empty body; ``replace`` on a non-empty body needs the UI
    to double-confirm; ``append`` is additive."""
    body = _scene_body(db, scene_id)
    is_empty = not body.strip()
    if requested == APPLY_CANCEL:
        return ("", False, "cancelled")
    if requested == APPLY_TO_EMPTY:
        if is_empty:
            return (APPLY_REPLACE, False, "")
        return ("", False, "The scene body is not empty — choose Replace or Append.")
    if requested == APPLY_REPLACE:
        return (APPLY_REPLACE, not is_empty, "")
    if requested == APPLY_APPEND:
        return (APPLY_APPEND, False, "")
    return ("", False, f"Unknown apply mode: {requested!r}")


def _compose_body(db, scene_id: int, script: sbk.SeriesScript,
                  effective_mode: str) -> str:
    """Compose the resulting Scene body for the mode. Append continues after the
    existing blocks (no overwrite)."""
    if effective_mode == APPLY_APPEND:
        existing = sbk.parse_series_text(_scene_body(db, scene_id))
        if not existing.is_empty():
            merged = sbk.SeriesScript(blocks=list(existing.blocks) + list(script.blocks))
            sbk._renumber(merged)
            return sbk.serialize_series_script(merged)
    return sbk.serialize_series_script(script)


def preview_draft_apply(db, project_id: int, scene_id: int,
                        script: sbk.SeriesScript, *, mode: str = APPLY_REPLACE):
    """Build a Controlled-Apply preview for the draft. **No mutation.** Returns the
    ApplyPreview, or None on a mode error."""
    effective, _confirm, err = resolve_apply_mode(db, project_id, scene_id, mode)
    if err:
        return None
    from logosforge.controlled_apply.service import build_apply_preview
    return build_apply_preview(
        db, project_id, target_type="scene", target_id=scene_id,
        proposed_text=_compose_body(db, scene_id, script, effective),
        apply_mode="replace", source_type="series_pipeline")


def apply_draft(db, project_id: int, scene_id: int,
                script: sbk.SeriesScript, *,
                mode: str = APPLY_REPLACE, confirmed: bool = False) -> dict:
    """Apply a Series draft to the Scene body via Controlled Apply.

    The AI never reaches here on its own: ``confirmed`` defaults to ``False`` and
    the underlying ``apply_operation`` refuses without it. The draft is validated
    (errors block) before any write; only ``Scene.content`` is touched — Outline
    summaries, Season/Arc and Episode plans, Timeline, PSYKE and Notes are left
    untouched."""
    if mode == APPLY_CANCEL:
        return {"ok": False, "cancelled": True}

    validation = validate_draft_series_script(script)
    if not validation.is_valid:
        return {"ok": False, "error": "Draft failed validation.",
                "validation": validation.to_dict()}

    effective, _confirm, err = resolve_apply_mode(db, project_id, scene_id, mode)
    if err:
        return {"ok": False, "error": err}

    from logosforge.controlled_apply.service import apply_operation
    return apply_operation(
        db, project_id, target_type="scene", target_id=scene_id,
        proposed_text=_compose_body(db, scene_id, script, effective),
        apply_mode="replace", confirmed=confirmed, source_type="series_pipeline")


# ===========================================================================
# Assistant / Logos context
# ===========================================================================


def series_planning_context(db, project_id: int, scene_id: int | None) -> str:
    """A short, labelled ``[Series Plan]`` block for the Assistant.

    Empty for non-series projects or scenes without a Season/Arc or Episode plan.
    Resolves the Act (Season) and Chapter (Episode) of the current scene."""
    if scene_id is None:
        return ""
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id, SERIES)
        if get_project_writing_mode_by_id(db, project_id) != SERIES:
            return ""
    except Exception:
        return ""
    meta = _scene_meta(db, scene_id)
    parts: list[str] = []
    if meta["act"]:
        season = get_season_plan(db, project_id, meta["act"])
        if season is not None and not season.is_empty():
            parts.append(f"Season / Arc ({meta['act']}):\n" + season.to_text())
    if meta["chapter"]:
        episode = get_episode_plan(db, project_id, meta["chapter"])
        if episode is not None and not episode.is_empty():
            parts.append(f"{sbk.episode_label(meta['chapter'])} beat plan:\n"
                         + episode.to_text())
    if not parts:
        return ""
    return "[Series Plan]\n" + "\n\n".join(parts)
