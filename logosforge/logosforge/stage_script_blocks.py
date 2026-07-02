"""Stage Script scene-body block adapter (Phase 1).

The foundation for Stage Script mode *inside the universal Manuscript section*:
a Scene's body (flat ``Scene.content`` text) is parsed into a structured, ordered
list of typed stage-play blocks and serialized back — no schema change, no
parallel storage, no separate Manuscript section. This mirrors how
``screenplay_blocks`` adapts a screenplay Scene body; the editor styles the stage
block grammar via ``writing_formats.STAGE_SCRIPT``.

A Stage Script Scene body uses a small, human-editable labelled grammar::

    SCENE: The Throne Room
    STAGE: A bare room. Evening.

    CHARACTER: MARIA
    (softly)
    It ends now.

    ENTER: John enters from stage left.
    LIGHT: Lights dim to blue.
    SOUND: Distant thunder.
    SET: A single chair, centre stage.
    TRANSITION: Blackout.
    NOTE: beat to land before the reveal.

Bare prose with no label loads safely as a Stage Direction (legacy plain text is
never destroyed). A ``CHARACTER:`` paragraph groups its following parenthetical /
dialogue lines.

Pure logic: parse / serialize / block operations / Markdown export / rule-based
validation / a small Assistant context block. No Qt, no LLM, no provider/API keys.
Outline summary (``Scene.summary``) is never read or written here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# -- Block taxonomy ----------------------------------------------------------
BT_SCENE_HEADING = "scene_heading"
BT_ACT_HEADING = "act_heading"
BT_STAGE_DIRECTION = "stage_direction"
BT_CHARACTER = "character"
BT_DIALOGUE = "dialogue"
BT_PARENTHETICAL = "parenthetical"
BT_ENTRANCE = "entrance"
BT_EXIT = "exit"
BT_LIGHTING_CUE = "lighting_cue"
BT_SOUND_CUE = "sound_cue"
BT_SET_PROPS = "set_props"
BT_TRANSITION = "transition"
BT_NOTE = "note"

BLOCK_TYPES = (
    BT_SCENE_HEADING, BT_ACT_HEADING, BT_STAGE_DIRECTION, BT_CHARACTER,
    BT_DIALOGUE, BT_PARENTHETICAL, BT_ENTRANCE, BT_EXIT, BT_LIGHTING_CUE,
    BT_SOUND_CUE, BT_SET_PROPS, BT_TRANSITION, BT_NOTE,
)
_VALID = set(BLOCK_TYPES)

# Cue-like blocks (validation + which need cue text / a character name).
_CUE_TYPES = (BT_LIGHTING_CUE, BT_SOUND_CUE, BT_SET_PROPS)
_MOVEMENT_TYPES = (BT_ENTRANCE, BT_EXIT)

# How each block_type maps to a STAGE_SCRIPT WritingFormat element for styling
# (entrance/exit/cues all render as the format's generic "cue" style).
_FORMAT_ELEMENT = {
    BT_SCENE_HEADING: "scene_heading", BT_ACT_HEADING: "act_heading",
    BT_STAGE_DIRECTION: "stage_direction", BT_CHARACTER: "character",
    BT_DIALOGUE: "dialogue", BT_PARENTHETICAL: "parenthetical",
    BT_ENTRANCE: "cue", BT_EXIT: "cue", BT_LIGHTING_CUE: "cue",
    BT_SOUND_CUE: "cue", BT_SET_PROPS: "cue", BT_TRANSITION: "transition",
    BT_NOTE: "note",
}

# Line-label aliases (case-insensitive) -> block_type, for parsing.
_LABEL_TO_TYPE = {
    "scene": BT_SCENE_HEADING, "scene heading": BT_SCENE_HEADING,
    "act": BT_ACT_HEADING, "act heading": BT_ACT_HEADING,
    "stage": BT_STAGE_DIRECTION, "stage direction": BT_STAGE_DIRECTION,
    "direction": BT_STAGE_DIRECTION,
    "character": BT_CHARACTER, "char": BT_CHARACTER,
    "dialogue": BT_DIALOGUE,
    "enter": BT_ENTRANCE, "entrance": BT_ENTRANCE,
    "exit": BT_EXIT,
    "light": BT_LIGHTING_CUE, "lighting": BT_LIGHTING_CUE,
    "lighting cue": BT_LIGHTING_CUE,
    "sound": BT_SOUND_CUE, "sound cue": BT_SOUND_CUE, "sfx": BT_SOUND_CUE,
    "set": BT_SET_PROPS, "props": BT_SET_PROPS, "set/props": BT_SET_PROPS,
    "transition": BT_TRANSITION, "blackout": BT_TRANSITION,
    "note": BT_NOTE, "general": BT_NOTE,
}

# block_type -> serialize label (character/dialogue/parenthetical are grouped).
_TYPE_TO_LABEL = {
    BT_SCENE_HEADING: "SCENE", BT_ACT_HEADING: "ACT",
    BT_STAGE_DIRECTION: "STAGE", BT_ENTRANCE: "ENTER", BT_EXIT: "EXIT",
    BT_LIGHTING_CUE: "LIGHT", BT_SOUND_CUE: "SOUND", BT_SET_PROPS: "SET",
    BT_TRANSITION: "TRANSITION", BT_NOTE: "NOTE", BT_DIALOGUE: "DIALOGUE",
}

# Validation thresholds (documented; conservative).
STAGE_DIRECTION_LONG_WORDS = 80      # one stage direction this long reads as dense
CONSECUTIVE_DIALOGUE_HIGH = 6        # this many dialogue blocks with no stage action

_LABEL_RE = re.compile(r"^\s*([A-Za-z][A-Za-z /]*?)\s*:\s*(.*)$")


def normalize_block_type(block_type: str | None) -> str:
    """Return a valid block type; unknown values fall back to Stage Direction
    (the safe home for legacy plain text)."""
    bt = (block_type or "").strip()
    return bt if bt in _VALID else BT_STAGE_DIRECTION


def format_element_for(block_type: str) -> str:
    """The STAGE_SCRIPT WritingFormat element name used to style *block_type*."""
    return _FORMAT_ELEMENT.get(normalize_block_type(block_type), "stage_direction")


@dataclass
class StageBlock:
    """One typed stage-play block (a paragraph-level unit)."""

    block_type: str
    text: str = ""
    scene_id: int | None = None
    order_index: int = 0
    character: str = ""          # speaker (for dialogue) — optional
    cue_label: str = ""          # cue label (for cue/movement blocks) — optional

    def __post_init__(self) -> None:
        self.block_type = normalize_block_type(self.block_type)

    def is_empty(self) -> bool:
        return not (self.text or "").strip() and not (self.character or "").strip()

    def to_dict(self) -> dict[str, Any]:
        return {"block_type": self.block_type, "text": self.text,
                "scene_id": self.scene_id, "order_index": self.order_index,
                "character": self.character, "cue_label": self.cue_label}

    @classmethod
    def from_dict(cls, d: dict) -> "StageBlock":
        d = d or {}
        return cls(block_type=d.get("block_type", BT_STAGE_DIRECTION),
                   text=d.get("text", "") or "", scene_id=d.get("scene_id"),
                   order_index=int(d.get("order_index", 0) or 0),
                   character=d.get("character", "") or "",
                   cue_label=d.get("cue_label", "") or "")


@dataclass
class StageScript:
    blocks: list[StageBlock] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(not b.is_empty() for b in self.blocks)

    def to_dict(self) -> dict[str, Any]:
        return {"blocks": [b.to_dict() for b in self.blocks]}

    @classmethod
    def from_dict(cls, d: dict) -> "StageScript":
        return cls(blocks=[StageBlock.from_dict(b) for b in ((d or {}).get("blocks") or [])])


# ===========================================================================
# Parse  (Scene body text -> ordered blocks)
# ===========================================================================


def _is_character_cue(line: str) -> bool:
    """Bare uppercase short line — e.g. ``MARIA`` — read as a character cue."""
    s = line.strip()
    if not s or len(s) > 35 or ":" in s:
        return False
    core = re.sub(r"\(.*?\)", "", s).strip()
    return bool(core) and bool(re.search(r"[A-Za-z]", core)) and core == core.upper()


def parse_stage_script_text(text: str) -> StageScript:
    """Parse a Stage Script Scene body into ordered blocks. Conservative and
    lossless: text with no labels loads as Stage Direction blocks (legacy plain
    text is never dropped)."""
    script = StageScript()
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return script

    order = 0

    def add(block_type: str, body: str, *, character: str = "",
            cue_label: str = "") -> None:
        nonlocal order
        script.blocks.append(StageBlock(
            block_type=block_type, text=body.strip(), order_index=order,
            character=character.strip(), cue_label=cue_label))
        order += 1

    # Blank-line-separated paragraphs (preserve intra-paragraph newlines).
    chunks = re.split(r"\n[ \t]*\n", raw)
    for chunk in chunks:
        lines = [ln for ln in chunk.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            continue
        first = lines[0].strip()

        m = _LABEL_RE.match(first)
        label = m.group(1).strip().lower() if m else ""
        bt = _LABEL_TO_TYPE.get(label) if m else None

        if bt == BT_CHARACTER:
            name = m.group(2).strip()
            add(BT_CHARACTER, name, character=name.upper())
            _emit_dialogue(lines[1:], name.upper(), add)
            continue
        if _is_character_cue(first):
            name = re.sub(r"\(.*?\)", "", first).strip().upper()
            add(BT_CHARACTER, first, character=name)
            _emit_dialogue(lines[1:], name, add)
            continue
        if bt is not None:
            rest = m.group(2)
            if len(lines) > 1:
                rest = (rest + "\n" + "\n".join(lines[1:])).strip()
            cue = _TYPE_TO_LABEL.get(bt, "") if bt in (_CUE_TYPES + _MOVEMENT_TYPES) else ""
            add(bt, rest, cue_label=cue)
            continue
        if first.startswith("(") and first.endswith(")") and len(first) >= 2:
            add(BT_PARENTHETICAL, first)
            continue
        # Unlabelled prose -> Stage Direction (lossless legacy compatibility).
        add(BT_STAGE_DIRECTION, "\n".join(ln.rstrip() for ln in lines))

    return script


def _emit_dialogue(lines, speaker, add) -> None:
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("(") and s.endswith(")"):
            add(BT_PARENTHETICAL, s)
        else:
            add(BT_DIALOGUE, s, character=speaker)


# ===========================================================================
# Serialize  (blocks -> Scene body text, round-trip safe)
# ===========================================================================


def serialize_stage_script(script: StageScript) -> str:
    paras: list[str] = []
    group: list[str] | None = None     # an open character/dialogue group

    def flush() -> None:
        nonlocal group
        if group:
            paras.append("\n".join(group))
        group = None

    for b in script.blocks:
        bt = b.block_type
        text = (b.text or "").strip()
        if bt == BT_CHARACTER:
            flush()
            name = (b.character or text).strip().upper()
            group = [f"CHARACTER: {name}"]
        elif bt == BT_DIALOGUE and group is not None:
            group.append(text)
        elif bt == BT_PARENTHETICAL and group is not None:
            group.append(text if text.startswith("(") else f"({text})")
        elif bt == BT_DIALOGUE:
            flush()
            paras.append(f"DIALOGUE: {text}")
        elif bt == BT_PARENTHETICAL:
            flush()
            paras.append(text if text.startswith("(") else f"({text})")
        else:
            flush()
            label = _TYPE_TO_LABEL.get(bt, "STAGE")
            paras.append(f"{label}: {text}")
    flush()
    return "\n\n".join(paras).strip() + ("\n" if paras else "")


# ===========================================================================
# Block operations (pure; mutate + renumber the script)
# ===========================================================================


def _renumber(script: StageScript) -> StageScript:
    for i, b in enumerate(script.blocks):
        b.order_index = i
    return script


def add_block(script: StageScript, block_type: str, text: str = "", *,
              character: str = "", cue_label: str = "",
              index: int | None = None) -> StageBlock:
    block = StageBlock(block_type=normalize_block_type(block_type), text=text,
                       character=character, cue_label=cue_label)
    if index is None or index >= len(script.blocks):
        script.blocks.append(block)
    else:
        script.blocks.insert(max(0, index), block)
    _renumber(script)
    return block


def move_block(script: StageScript, index: int, delta: int) -> bool:
    j = index + delta
    if 0 <= index < len(script.blocks) and 0 <= j < len(script.blocks):
        script.blocks[index], script.blocks[j] = script.blocks[j], script.blocks[index]
        _renumber(script)
        return True
    return False


def delete_block(script: StageScript, index: int) -> bool:
    if 0 <= index < len(script.blocks):
        script.blocks.pop(index)
        _renumber(script)
        return True
    return False


def character_cues(script: StageScript) -> list[str]:
    """Unique, order-preserving uppercased character cues in the script."""
    seen: set[str] = set()
    out: list[str] = []
    for b in script.blocks:
        if b.block_type == BT_CHARACTER:
            name = (b.character or re.sub(r"\(.*?\)", "", b.text)).strip().upper()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return out


# ===========================================================================
# Scene-body DB adapter (the Scene body IS the storage — no schema change)
# ===========================================================================


def load_scene_script(db, scene_id: int) -> StageScript:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return StageScript()
    return parse_stage_script_text(getattr(scene, "content", "") or "")


def save_scene_script(db, scene_id: int, script: StageScript) -> None:
    """Write the stage-play script to the Scene *body* only. Never touches the
    Outline summary, PSYKE, Timeline, or any other field."""
    db.update_scene_content(scene_id, serialize_stage_script(script))


# ===========================================================================
# Markdown export
# ===========================================================================


def scene_markdown(script: StageScript, *, title: str = "") -> str:
    out: list[str] = [f"# {title or 'Untitled Scene'}", ""]
    if script.is_empty():
        out.append("_(no stage script)_")
        return "\n".join(out)
    for b in script.blocks:
        text = (b.text or "").strip()
        bt = b.block_type
        if bt == BT_SCENE_HEADING:
            out.append(f"## {text}")
        elif bt == BT_ACT_HEADING:
            out.append(f"# {text}")
        elif bt == BT_CHARACTER:
            out.append("")
            out.append((b.character or text).strip().upper())
        elif bt == BT_DIALOGUE:
            out.append(text)
        elif bt == BT_PARENTHETICAL:
            out.append(text if text.startswith("(") else f"({text})")
        elif bt == BT_STAGE_DIRECTION:
            out.append("")
            out.append(f"[Stage Direction] {text}")
        else:
            label = {BT_ENTRANCE: "Entrance", BT_EXIT: "Exit",
                     BT_LIGHTING_CUE: "Lighting Cue", BT_SOUND_CUE: "Sound Cue",
                     BT_SET_PROPS: "Set / Props", BT_TRANSITION: "Transition",
                     BT_NOTE: "Note"}.get(bt, "Note")
            out.append("")
            out.append(f"[{label}] {text}")
    return "\n".join(out).rstrip() + "\n"


def export_scene_markdown(db, project_id: int, scene_id: int) -> str:
    scene = db.get_scene_by_id(scene_id)
    title = (getattr(scene, "title", "") or "Untitled Scene") if scene else "Scene"
    return scene_markdown(load_scene_script(db, scene_id), title=title)


def export_project_markdown(db, project_id: int) -> str:
    """Full project stage script in canonical Act->Chapter->Scene order. Body only
    — never Outline summaries, Timeline notes, or provider settings."""
    from logosforge import story_structure as ss
    project = db.get_project_by_id(project_id)
    out: list[str] = [f"# {getattr(project, 'title', 'Stage Script')}", ""]
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
class StageValidation:
    warnings: list[str] = field(default_factory=list)
    is_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"warnings": list(self.warnings), "is_valid": self.is_valid}


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def validate_stage_script(script: StageScript) -> StageValidation:
    """Rule-based Stage Script warnings (no LLM). Warnings are advisory; an empty
    script is the only thing flagged as not-valid-for-export."""
    report = StageValidation()
    if script.is_empty():
        report.warnings.append("Scene has no stage script — add a stage direction "
                               "or a character and dialogue.")
        report.is_valid = False
        return report

    blocks = script.blocks
    has_speaker = False
    consecutive_dialogue = 0
    has_stage_action = False

    for i, b in enumerate(blocks):
        bt = b.block_type
        if b.is_empty() and bt not in (BT_CHARACTER,):
            report.warnings.append(f"Block {i + 1} ({bt}) is empty.")

        if bt in (BT_STAGE_DIRECTION,) + _MOVEMENT_TYPES + _CUE_TYPES:
            has_stage_action = True

        if bt == BT_CHARACTER:
            has_speaker = True
            consecutive_dialogue = 0
            # Character with no following dialogue (skip parentheticals).
            nxt = next((nb for nb in blocks[i + 1:]
                        if nb.block_type != BT_PARENTHETICAL), None)
            if nxt is None or nxt.block_type != BT_DIALOGUE:
                report.warnings.append(
                    f"{(b.character or b.text).strip().upper() or 'Character'} has a "
                    "cue but no following dialogue.")
        elif bt == BT_DIALOGUE:
            if not has_speaker:
                report.warnings.append(
                    f"Block {i + 1}: dialogue with no preceding character cue.")
            consecutive_dialogue += 1
            if consecutive_dialogue == CONSECUTIVE_DIALOGUE_HIGH:
                report.warnings.append(
                    "Several dialogue blocks in a row with no stage action — add "
                    "blocking, business, or a beat.")
        elif bt == BT_PARENTHETICAL:
            pass  # keeps the speaker/dialogue run open
        else:
            has_speaker = False
            consecutive_dialogue = 0

        if bt == BT_STAGE_DIRECTION and _words(b.text) >= STAGE_DIRECTION_LONG_WORDS:
            report.warnings.append(f"Block {i + 1}: stage direction is long.")
        if bt in _CUE_TYPES and not b.text.strip():
            report.warnings.append(f"Block {i + 1}: {bt.replace('_', ' ')} has no cue text.")
        if bt in _MOVEMENT_TYPES and not b.text.strip():
            report.warnings.append(
                f"Block {i + 1}: {bt} has no character / movement text.")

    if any(b.block_type == BT_DIALOGUE for b in blocks) and not has_stage_action:
        report.warnings.append("No visible stage action — the scene is all talk; "
                               "add blocking, entrances/exits, or cues.")

    report.warnings = list(dict.fromkeys(report.warnings))
    return report


# ===========================================================================
# Assistant / Logos context (minimal)
# ===========================================================================


def stage_script_context(db, project_id: int, scene_id: int | None) -> str:
    """A short, labelled ``[Stage Script]`` block for Assistant context.

    Empty for non-stage-script projects or scenes without stage content."""
    if scene_id is None:
        return ""
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id, STAGE_SCRIPT,
        )
        if get_project_writing_mode_by_id(db, project_id) != STAGE_SCRIPT:
            return ""
    except Exception:
        return ""
    script = load_scene_script(db, scene_id)
    if script.is_empty():
        return ""
    return (f"[Stage Script]\n{len(script.blocks)} block(s); "
            f"{len(character_cues(script))} speaking character(s).")
