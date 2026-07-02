"""Screenplay block model + conservative parser/serializer (Phase 10B).

Turns flat scene text into a list of typed :class:`ScreenplayBlock`s and back,
*without* any DB schema change — blocks are derived from paragraphs on demand
(scene content is still stored as flat text; per-block persistence is Phase 10C).

Design rules:
* element types come from the Phase 10A taxonomy (``logosforge.screenplay``);
* the parser is conservative — when a line's role is uncertain it becomes
  ``action`` (never a false ``character``/``transition``);
* the serializer never loses or silently reorders text; it only uppercases the
  caps elements and normalizes parenthetical wrapping;
* pure logic — no Qt, no LLM, no DB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay as sp


def normalize_element_type(element_type: str | None) -> str:
    """Return a valid taxonomy element key; unknown values fall back to ``action``."""
    et = (element_type or "").strip()
    return et if sp.is_valid_element(et) else "action"


@dataclass
class ScreenplayBlock:
    """One typed screenplay block (a paragraph-level unit)."""

    element_type: str
    text: str
    scene_id: int | None = None
    order_index: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Centralized validation: invalid types degrade safely to action.
        self.element_type = normalize_element_type(self.element_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_type": self.element_type,
            "text": self.text,
            "scene_id": self.scene_id,
            "order_index": self.order_index,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScreenplayBlock":
        return cls(
            element_type=d.get("element_type", "action"),
            text=d.get("text", ""),
            scene_id=d.get("scene_id"),
            order_index=int(d.get("order_index", 0)),
            metadata=dict(d.get("metadata", {})),
        )


# -- Line classifiers (conservative) -----------------------------------------

_TRANSITION_LITERALS = {
    "FADE IN:", "FADE OUT.", "FADE OUT", "FADE TO BLACK.", "CUT TO:",
    "SMASH CUT TO:", "MATCH CUT TO:", "DISSOLVE TO:", "JUMP CUT TO:",
}


def _is_scene_heading(line: str) -> bool:
    s = line.strip().upper()
    return any(s.startswith(p) for p in sp.SCENE_HEADING_PREFIXES)


def _is_transition(line: str) -> bool:
    s = line.strip()
    if not s or s != s.upper():       # transitions are uppercase
        return False
    if s in _TRANSITION_LITERALS or s.startswith("FADE "):
        return True
    return s.endswith("TO:")


def _is_character_cue(line: str) -> bool:
    """Uppercase, short cue line — e.g. ``JOHN`` or ``JOHN (V.O.)``.

    Conservative: must be uppercase, contain letters, and be short. Trailing
    extensions in parentheses are allowed and ignored for the caps test.
    """
    s = line.strip()
    if not s or len(s) > 35:
        return False
    core = re.sub(r"\(.*?\)", "", s).strip()   # drop (V.O.) / (CONT'D)
    if not core or not re.search(r"[A-Za-z]", core):
        return False
    return core == core.upper()


def _is_parenthetical(line: str) -> bool:
    s = line.strip()
    return len(s) >= 2 and s.startswith("(") and s.endswith(")")


def _is_note(line: str) -> bool:
    # Fountain note syntax: [[ ... ]] on its own line.
    s = line.strip()
    return len(s) >= 4 and s.startswith("[[") and s.endswith("]]")


def parse_screenplay_text(
    text: str, scene_id: int | None = None,
) -> list[ScreenplayBlock]:
    """Derive a list of :class:`ScreenplayBlock`s from flat scene text.

    Blocks are separated by blank lines. Within a 'dialogue chunk' (a chunk whose
    first line is a character cue), the cue + parentheticals + dialogue are split
    into their own blocks. Everything uncertain becomes ``action`` — no text is
    dropped, order is preserved.
    """
    blocks: list[ScreenplayBlock] = []
    if not text or not text.strip():
        return blocks

    order = 0

    def add(element_type: str, body: str) -> None:
        nonlocal order
        if body == "":
            return
        blocks.append(ScreenplayBlock(
            element_type=element_type, text=body,
            scene_id=scene_id, order_index=order,
        ))
        order += 1

    # Split into blank-line-separated chunks, preserving intra-chunk newlines.
    chunks = re.split(r"\n[ \t]*\n", text.replace("\r\n", "\n").replace("\r", "\n"))

    for chunk in chunks:
        lines = [ln for ln in chunk.split("\n")]
        # Drop leading/trailing fully-empty lines but keep internal structure.
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            continue

        first = lines[0].strip()

        # Single-line structural chunks.
        if len(lines) == 1:
            if _is_scene_heading(first):
                add("scene_heading", first)
            elif _is_transition(first):
                add("transition", first)
            elif _is_note(first):
                add("note", first[2:-2].strip())   # strip [[ ]]
            else:
                add("action", lines[0].rstrip())
            continue

        # Multi-line chunk starting with a character cue → dialogue group.
        if _is_character_cue(first) and not _is_scene_heading(first):
            add("character", first)
            for ln in lines[1:]:
                if not ln.strip():
                    continue
                if _is_parenthetical(ln):
                    add("parenthetical", ln.strip())
                else:
                    add("dialogue", ln.rstrip())
            continue

        # A scene heading that happens to lead a multi-line chunk.
        if _is_scene_heading(first):
            add("scene_heading", first)
            rest = "\n".join(lines[1:]).strip()
            if rest:
                add("action", rest)
            continue

        # Otherwise the whole chunk is one action paragraph (preserve newlines).
        add("action", "\n".join(ln.rstrip() for ln in lines))

    return blocks


# -- Serialization ------------------------------------------------------------


def _format_block_text(block: ScreenplayBlock, *, uppercase: bool) -> str:
    text = block.text
    if uppercase and sp.is_uppercase_element(block.element_type):
        text = text.upper()
    if block.element_type == "parenthetical":
        s = text.strip()
        if not (s.startswith("(") and s.endswith(")")):
            text = f"({s})"
    return text


def serialize_blocks(
    blocks: list[ScreenplayBlock], *, uppercase: bool = True,
) -> str:
    """Render blocks back to plain screenplay text.

    Round-trip safe: no text loss, order preserved; caps elements are uppercased
    and parentheticals normalized. A character cue and its following
    parentheticals/dialogue are kept together as ONE blank-line-separated
    paragraph (single newlines within the group) so that re-parsing the output
    reconstructs the same character/dialogue blocks rather than degrading the cue
    to an action line.
    """
    paras: list[str] = []
    group: list[str] | None = None   # an open character/dialogue group

    def flush() -> None:
        nonlocal group
        if group:
            paras.append("\n".join(group))
        group = None

    for b in blocks:
        text = _format_block_text(b, uppercase=uppercase)
        if b.element_type == "character":
            flush()
            group = [text]
        elif b.element_type in ("parenthetical", "dialogue") and group is not None:
            group.append(text)
        else:
            flush()
            paras.append(text)
    flush()
    return "\n\n".join(paras)


def to_fountain(blocks: list[ScreenplayBlock]) -> str:
    """Render blocks as Fountain-like text.

    Conservative Fountain conventions: forced scene headings (``.``) only when
    the heading doesn't already start with a recognized prefix; transitions as
    ``> ...`` when not auto-detectable; notes as ``[[...]]``.
    """
    out: list[str] = []
    for b in blocks:
        et = b.element_type
        text = b.text.strip()
        if et == "scene_heading":
            up = text.upper()
            if any(up.startswith(p) for p in sp.SCENE_HEADING_PREFIXES):
                out.append(up)
            else:
                out.append("." + up)
        elif et == "transition":
            up = text.upper()
            out.append(up if up.endswith("TO:") else f"> {up}")
        elif et == "character":
            out.append(text.upper())
        elif et == "parenthetical":
            s = text
            out.append(s if s.startswith("(") else f"({s})")
        elif et == "note":
            out.append(f"[[{text}]]")
        elif et == "shot":
            out.append(text.upper())
        else:  # action, dialogue
            out.append(text)
    return "\n\n".join(out)


def character_cues(blocks: list[ScreenplayBlock]) -> list[str]:
    """Unique, order-preserving uppercased character cues present in *blocks*."""
    seen: set[str] = set()
    out: list[str] = []
    for b in blocks:
        if b.element_type == "character":
            # Strip extensions like (V.O.) for the canonical cue name.
            name = re.sub(r"\(.*?\)", "", b.text).strip().upper()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return out
