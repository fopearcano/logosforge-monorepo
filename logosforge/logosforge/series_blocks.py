"""Series / teleplay scene-body block adapter (Phase 1).

The foundation for Series mode *inside the universal Manuscript section*: a
Scene's body (flat ``Scene.content`` text) is parsed into a structured, ordered
list of typed teleplay blocks and serialized back — no schema change, no parallel
storage, no separate Manuscript section, and **no new Season/Episode storage**.

Series writing is screenplay-like, so this adapter **reuses the screenplay block
engine** (:mod:`logosforge.screenplay_blocks`) for the screenplay subset (scene
headings, action, character, dialogue, parenthetical, transition, shot) and adds
only the serial-specific markers — Act Break, Teaser / Cold Open, Tag — on top via
conservative reclassification. ``screenplay_blocks`` is never modified, so
Screenplay mode is preserved.

The canonical structure is unchanged (Act → Chapter → Scene); Series mode merely
*displays* Chapter as Episode where useful (see :func:`episode_label`).

Pure logic: parse / serialize / block operations / Markdown export / rule-based
validation / a small Assistant context block. No Qt, no LLM, no provider/API keys.
Outline summary (``Scene.summary``) is never read or written here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb

# -- Block taxonomy ----------------------------------------------------------
# Screenplay-reused types (valid screenplay element keys, pass through unchanged):
BT_SCENE_HEADING = "scene_heading"
BT_ACTION = "action"
BT_CHARACTER = "character"
BT_DIALOGUE = "dialogue"
BT_PARENTHETICAL = "parenthetical"
BT_TRANSITION = "transition"
BT_SHOT = "shot"
BT_NOTE = "note"
# Series-specific markers:
BT_ACT_BREAK = "act_break"
BT_TEASER = "teaser"          # teaser / cold open
BT_TAG = "tag"

BLOCK_TYPES = (
    BT_SCENE_HEADING, BT_ACTION, BT_CHARACTER, BT_DIALOGUE, BT_PARENTHETICAL,
    BT_TRANSITION, BT_SHOT, BT_ACT_BREAK, BT_TEASER, BT_TAG, BT_NOTE,
)
_VALID = set(BLOCK_TYPES)
_SERIES_MARKERS = (BT_ACT_BREAK, BT_TEASER, BT_TAG)
# Series markers serialize as caps-standalone lines (re-parse + reclassify
# reconstructs them); "transition" is the screenplay element with that shape.
_MARKER_SERIALIZE_AS = "transition"

# Validation thresholds (documented; conservative).
CONSECUTIVE_DIALOGUE_HIGH = 6

_ACT_NUM = re.compile(r"^ACT (ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|\d+)\b")


def normalize_block_type(block_type: str | None) -> str:
    """Return a valid block type; unknown values fall back to Action (the safe
    home for legacy plain text, matching the screenplay default)."""
    bt = (block_type or "").strip()
    return bt if bt in _VALID else BT_ACTION


def episode_label(chapter: str | int) -> str:
    """Series displays a Chapter as an Episode. Pure label mapping — the internal
    canonical unit remains Chapter; no storage change."""
    c = str(chapter).strip()
    if not c:
        return "Episode"
    return c if c.lower().startswith("episode") else f"Episode {c}"


def _series_marker(text: str) -> str | None:
    """Classify a short line as a serial marker (Act Break / Teaser / Tag), else
    None. Conservative: brackets are stripped and the test is exact/prefix on the
    uppercased text so real character cues never match."""
    s = re.sub(r"^[\[(]+|[\])]+$", "", (text or "").strip()).strip().upper()
    if not s:
        return None
    if s in ("TEASER", "COLD OPEN") or s.startswith(("TEASER ", "COLD OPEN ")):
        return BT_TEASER
    if s == "TAG":
        return BT_TAG
    if (s in ("ACT BREAK", "ACT IN", "ACT OUT") or s.startswith("ACT BREAK")
            or s.startswith("END OF ACT") or s.startswith("END OF EPISODE")
            or _ACT_NUM.match(s)):
        return BT_ACT_BREAK
    return None


@dataclass
class SeriesBlock:
    block_type: str
    text: str = ""
    scene_id: int | None = None
    order_index: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.block_type = normalize_block_type(self.block_type)

    def is_empty(self) -> bool:
        return not (self.text or "").strip()

    def to_dict(self) -> dict[str, Any]:
        return {"block_type": self.block_type, "text": self.text,
                "scene_id": self.scene_id, "order_index": self.order_index,
                "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, d: dict) -> "SeriesBlock":
        d = d or {}
        return cls(block_type=d.get("block_type", BT_ACTION),
                   text=d.get("text", "") or "", scene_id=d.get("scene_id"),
                   order_index=int(d.get("order_index", 0) or 0),
                   metadata=dict(d.get("metadata", {})))


@dataclass
class SeriesScript:
    blocks: list[SeriesBlock] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(not b.is_empty() for b in self.blocks)

    def to_dict(self) -> dict[str, Any]:
        return {"blocks": [b.to_dict() for b in self.blocks]}

    @classmethod
    def from_dict(cls, d: dict) -> "SeriesScript":
        return cls(blocks=[SeriesBlock.from_dict(b) for b in ((d or {}).get("blocks") or [])])


# ===========================================================================
# Parse  (reuse the screenplay engine + reclassify serial markers)
# ===========================================================================


def parse_series_text(text: str) -> SeriesScript:
    """Parse a Series Scene body into ordered blocks. Reuses the screenplay parser
    and reclassifies serial markers; legacy plain text loads as Action (lossless)."""
    script = SeriesScript()
    for i, b in enumerate(sb.parse_screenplay_text(text)):
        bt = b.element_type
        if bt in (BT_CHARACTER, BT_TRANSITION, BT_ACTION) and len(b.text.strip()) <= 40:
            marker = _series_marker(b.text)
            if marker:
                bt = marker
        script.blocks.append(SeriesBlock(block_type=bt, text=b.text, order_index=i,
                                         metadata=dict(b.metadata)))
    return script


# ===========================================================================
# Serialize  (reuse the screenplay serializer; markers -> caps-standalone)
# ===========================================================================


def serialize_series_script(script: SeriesScript) -> str:
    sblocks: list[sb.ScreenplayBlock] = []
    for b in script.blocks:
        et = _MARKER_SERIALIZE_AS if b.block_type in _SERIES_MARKERS else b.block_type
        sblocks.append(sb.ScreenplayBlock(element_type=et, text=b.text))
    return sb.serialize_blocks(sblocks)


# ===========================================================================
# Block operations (pure; mutate + renumber)
# ===========================================================================


def _renumber(script: SeriesScript) -> SeriesScript:
    for i, b in enumerate(script.blocks):
        b.order_index = i
    return script


def add_block(script: SeriesScript, block_type: str, text: str = "", *,
              index: int | None = None, **metadata) -> SeriesBlock:
    block = SeriesBlock(block_type=normalize_block_type(block_type), text=text,
                        metadata=dict(metadata))
    if index is None or index >= len(script.blocks):
        script.blocks.append(block)
    else:
        script.blocks.insert(max(0, index), block)
    _renumber(script)
    return block


def move_block(script: SeriesScript, index: int, delta: int) -> bool:
    j = index + delta
    if 0 <= index < len(script.blocks) and 0 <= j < len(script.blocks):
        script.blocks[index], script.blocks[j] = script.blocks[j], script.blocks[index]
        _renumber(script)
        return True
    return False


def delete_block(script: SeriesScript, index: int) -> bool:
    if 0 <= index < len(script.blocks):
        script.blocks.pop(index)
        _renumber(script)
        return True
    return False


def character_cues(script: SeriesScript) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for b in script.blocks:
        if b.block_type == BT_CHARACTER:
            name = re.sub(r"\(.*?\)", "", b.text).strip().upper()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return out


# ===========================================================================
# Scene-body DB adapter (the Scene body IS the storage — no schema change)
# ===========================================================================


def load_scene_script(db, scene_id: int) -> SeriesScript:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return SeriesScript()
    return parse_series_text(getattr(scene, "content", "") or "")


def save_scene_script(db, scene_id: int, script: SeriesScript) -> None:
    """Write the teleplay script to the Scene *body* only. Never touches the
    Outline summary, PSYKE, Timeline, or any other field."""
    db.update_scene_content(scene_id, serialize_series_script(script))


# ===========================================================================
# Markdown export
# ===========================================================================

_MARKER_LABEL = {BT_ACT_BREAK: "Act Break", BT_TEASER: "Teaser / Cold Open",
                 BT_TAG: "Tag", BT_TRANSITION: "Transition", BT_SHOT: "Shot",
                 BT_NOTE: "Note"}


def scene_markdown(script: SeriesScript, *, title: str = "", episode: str = "") -> str:
    head = f"# {title or 'Untitled Scene'}"
    out: list[str] = [head]
    if episode.strip():
        out.append(f"_{episode_label(episode)}_")
    out.append("")
    if script.is_empty():
        out.append("_(no script)_")
        return "\n".join(out)
    for b in script.blocks:
        text = (b.text or "").strip()
        bt = b.block_type
        if bt == BT_SCENE_HEADING:
            out.append("")
            out.append(f"[Scene Heading] {text}")
        elif bt == BT_ACTION:
            out.append("")
            out.append(f"[Action] {text}")
        elif bt == BT_CHARACTER:
            out.append("")
            out.append(text.upper())
        elif bt == BT_DIALOGUE:
            out.append(text)
        elif bt == BT_PARENTHETICAL:
            out.append(text if text.startswith("(") else f"({text})")
        else:
            out.append("")
            out.append(f"[{_MARKER_LABEL.get(bt, 'Note')}] {text}")
    return "\n".join(out).rstrip() + "\n"


def export_scene_markdown(db, project_id: int, scene_id: int) -> str:
    scene = db.get_scene_by_id(scene_id)
    title = (getattr(scene, "title", "") or "Untitled Scene") if scene else "Scene"
    episode = (getattr(scene, "chapter", "") or "") if scene else ""
    return scene_markdown(load_scene_script(db, scene_id), title=title, episode=episode)


def export_project_markdown(db, project_id: int) -> str:
    """Full project teleplay in canonical Act->Chapter->Scene order (Chapter shown
    as Episode). Body only — never Outline summaries, Timeline notes, or settings."""
    from logosforge import story_structure as ss
    project = db.get_project_by_id(project_id)
    out: list[str] = [f"# {getattr(project, 'title', 'Series')}", ""]
    try:
        order = ss.canonical_scene_order(db, project_id)
    except Exception:
        order = [s.id for s in db.get_all_scenes(project_id)]
    for sid in order:
        out.append(export_scene_markdown(db, project_id, sid).rstrip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ===========================================================================
# Deterministic validation
# ===========================================================================


@dataclass
class SeriesValidation:
    warnings: list[str] = field(default_factory=list)
    is_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"warnings": list(self.warnings), "is_valid": self.is_valid}


def validate_series_script(script: SeriesScript) -> SeriesValidation:
    """Rule-based Series script warnings (no LLM). Warnings are advisory; an empty
    script is the only thing flagged as not-valid-for-export."""
    report = SeriesValidation()
    if script.is_empty():
        report.warnings.append("Scene has no script — add a scene heading, action, "
                               "or character and dialogue.")
        report.is_valid = False
        return report

    blocks = script.blocks
    has_speaker = False
    consecutive_dialogue = 0
    has_action = False

    for i, b in enumerate(blocks):
        bt = b.block_type
        if b.is_empty() and bt != BT_CHARACTER:
            report.warnings.append(f"Block {i + 1} ({bt}) is empty.")
        if bt in (BT_ACTION, BT_SCENE_HEADING, BT_SHOT):
            has_action = True
        if bt == BT_CHARACTER:
            has_speaker = True
            consecutive_dialogue = 0
            nxt = next((nb for nb in blocks[i + 1:]
                        if nb.block_type != BT_PARENTHETICAL), None)
            if nxt is None or nxt.block_type != BT_DIALOGUE:
                report.warnings.append(
                    f"{(b.text or 'Character').strip().upper()} has a cue but no "
                    "following dialogue.")
        elif bt == BT_DIALOGUE:
            if not has_speaker:
                report.warnings.append(
                    f"Block {i + 1}: dialogue with no preceding character cue.")
            consecutive_dialogue += 1
            if consecutive_dialogue == CONSECUTIVE_DIALOGUE_HIGH:
                report.warnings.append(
                    "Several dialogue blocks in a row with no action — add a beat.")
        elif bt == BT_PARENTHETICAL:
            pass
        else:
            has_speaker = False
            consecutive_dialogue = 0
        # Act Break at the very start reads oddly.
        if bt == BT_ACT_BREAK and i == 0:
            report.warnings.append("Act Break appears at the start of the scene.")

    if not any(b.block_type == BT_SCENE_HEADING for b in blocks):
        report.warnings.append("No scene heading.")
    if any(b.block_type == BT_DIALOGUE for b in blocks) and not has_action:
        report.warnings.append("No visible action — the scene is all talk.")

    report.warnings = list(dict.fromkeys(report.warnings))
    return report


# ===========================================================================
# Assistant / Logos context (minimal)
# ===========================================================================


def series_context(db, project_id: int, scene_id: int | None) -> str:
    """A short, labelled ``[Series Script]`` block for Assistant context.

    Empty for non-series projects or scenes without script content."""
    if scene_id is None:
        return ""
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id, SERIES,
        )
        if get_project_writing_mode_by_id(db, project_id) != SERIES:
            return ""
    except Exception:
        return ""
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return ""
    script = load_scene_script(db, scene_id)
    if script.is_empty():
        return ""
    episode = episode_label(getattr(scene, "chapter", "") or "")
    return (f"[Series Script]\n{episode} · {len(script.blocks)} block(s); "
            f"{len(character_cues(script))} speaking character(s).")
