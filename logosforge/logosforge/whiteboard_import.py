"""Graduate a Free-tier **Whiteboard** document into a Pro/core project.

The Free "Whiteboard" app stores a manuscript as a single block document
(``~/.logosforge/whiteboards/{id}.json``): an ordered list of typed rich-text
blocks — ``paragraph`` / ``heading`` (with a ``level``) carrying inline
bold/italic ``marks`` (``{type:'bold'|'italic', from, to}`` char offsets) — under
a ``mode`` (novel / screenplay / graphic_novel / stage_script). Pro and the core
instead store a manuscript as ordered :class:`Scene` rows whose ``content`` is
flat text.

This module bridges the two — the one-way **Free → Pro "graduate my draft"**
path — by (1) segmenting the flowing block document into scenes and (2)
serializing each segment's blocks into scene ``content`` in the flat grammar the
core's export + format-intelligence already read. It mirrors the Whiteboard's own
``blocksToFountainText`` (heading → ``#``×level, else raw text) and additionally
re-applies the ``marks`` as Fountain/markdown ``**bold**`` / ``*italic*`` for prose
modes (the Whiteboard export drops them; screenplay text already carries literal
markers, so marks are only applied for prose).

Pure logic — no Qt, no LLM, no network. One-way (blocks → scenes).
"""

from __future__ import annotations

import re
from typing import Any

from logosforge import writing_modes

# A screenplay scene break: a slug line (INT./EXT./EST./I/E) or a '.'-forced
# heading (a single leading dot, but not an ellipsis).
_SCENE_HEADING = re.compile(r"^\s*(INT|EXT|EST|INT\.?/EXT|I/E)[.\s]", re.IGNORECASE)
_FORCED_HEADING = re.compile(r"^\s*\.[^.\s]")


def _apply_marks(text: str, marks: list[dict] | None) -> str:
    """Wrap bold/italic char-ranges as ``**bold**`` / ``*italic*``.

    ``marks`` are ``{type, from, to}`` char offsets into *text* (from inclusive,
    to exclusive). Ranges of different types may overlap; we emit close-then-open
    at each boundary. Malformed marks are skipped rather than raising.
    """
    if not marks or not text:
        return text
    n = len(text)
    opens: dict[int, list[str]] = {}
    closes: dict[int, list[str]] = {}
    for m in marks:
        if not isinstance(m, dict):
            continue
        mt = str(m.get("type", ""))
        try:
            a, b = int(m.get("from", 0)), int(m.get("to", 0))
        except (TypeError, ValueError):
            continue
        if mt not in ("bold", "italic") or a < 0 or b > n or a >= b:
            continue
        tok = "**" if mt == "bold" else "*"
        opens.setdefault(a, []).append(tok)
        closes.setdefault(b, []).append(tok)
    if not opens and not closes:
        return text
    out: list[str] = []
    for i in range(n + 1):
        out.extend(closes.get(i, []))
        out.extend(opens.get(i, []))
        if i < n:
            out.append(text[i])
    return "".join(out)


def _render_block(b: dict, apply_marks: bool) -> str:
    text = str(b.get("text", "") or "")
    return _apply_marks(text, b.get("marks")) if apply_marks else text


def _is_scene_break(b: dict, screenplay: bool) -> bool:
    if str(b.get("type", "")) == "heading":
        return True
    if screenplay:
        t = str(b.get("text", "") or "")
        return bool(_SCENE_HEADING.match(t) or _FORCED_HEADING.match(t))
    return False


def segment_blocks(doc: dict) -> tuple[list[dict[str, str]], list[int]]:
    """Segment a whiteboard block-document into scenes AND a block→scene map.

    Returns ``(scenes, block_to_scene)``:
    - ``scenes`` — the ``[{title, content}]`` list (see :func:`blocks_to_scenes`).
    - ``block_to_scene`` — aligned to ``doc['blocks']``; ``block_to_scene[i]`` is
      the 0-based ordinal of the scene that source block ``i`` contributes to
      (``-1`` for a block that precedes any scene / can't be segmented). The map
      lets a caller resolve a block-anchored link to the scene it landed in.

    A break block (a ``heading``, or in screenplay/series mode a slug line) closes
    the current scene and opens a new one, so it belongs to the NEW scene.
    """
    mode = writing_modes.normalize_mode(str(doc.get("mode") or "novel"))
    blocks = doc.get("blocks") or []
    doc_title = str(doc.get("title") or "").strip() or "Untitled"
    screenplay = mode in ("screenplay", "series")
    apply_marks = not screenplay  # screenplay encodes emphasis as literal markers
    para_sep = "\n\n" if mode == "novel" else "\n"

    scenes: list[dict[str, str]] = []
    block_to_scene: list[int] = [-1] * len(blocks)
    cur_title: str | None = None
    cur_lines: list[str] = []
    started = False

    def flush() -> None:
        nonlocal cur_title, cur_lines, started
        if not started:
            return
        title = (cur_title or doc_title or "").strip()[:120] or f"Scene {len(scenes) + 1}"
        body = para_sep.join(cur_lines).strip()
        scenes.append({"title": title, "content": body})
        cur_title, cur_lines = None, []

    for idx, b in enumerate(blocks):
        if not isinstance(b, dict):
            block_to_scene[idx] = len(scenes) if started else -1
            continue
        if _is_scene_break(b, screenplay):
            flush()  # close the previous scene first
            started = True
            cur_title = str(b.get("text", "") or "").strip()
            cur_lines = []
            if screenplay and str(b.get("type", "")) != "heading":
                cur_lines.append(_render_block(b, apply_marks))  # slug stays in the body
            block_to_scene[idx] = len(scenes)  # the break block belongs to the NEW scene
        else:
            started = True
            block_to_scene[idx] = len(scenes)  # the in-progress scene's future ordinal
            line = _render_block(b, apply_marks)
            if mode == "novel" and not line.strip():
                continue  # blank paragraphs are implied by the \n\n join
            cur_lines.append(line)
    flush()

    if not scenes:
        scenes.append({"title": doc_title, "content": ""})
    return scenes, block_to_scene


def blocks_to_scenes(doc: dict) -> list[dict[str, str]]:
    """Segment a whiteboard block-document into ``[{title, content}]`` scenes.

    A new scene starts at each ``heading`` block (its text → the scene title) and,
    in screenplay/series mode, at each slug line (kept in the body). Prose is
    joined blank-line-separated (paragraphs); screenplay/GN/stage line-by-line, so
    the mode's parser round-trips. With no break markers the whole document becomes
    a single scene. (Thin wrapper over :func:`segment_blocks`.)
    """
    return segment_blocks(doc)[0]


def import_whiteboard_document(db, doc: dict, *, title: str | None = None) -> dict[str, Any]:
    """Create a NEW project from a whiteboard document and populate its scenes.

    Returns ``{project_id, title, mode, scenes_created, scene_titles}``. The new
    project's writing mode matches the document's ``mode`` so the core's format
    intelligence + export work immediately.
    """
    mode = writing_modes.normalize_mode(str(doc.get("mode") or "novel"))
    proj_title = title or str(doc.get("title") or "").strip() or "Imported from Whiteboard"
    try:
        default_fmt = writing_modes.default_writing_format(mode)
    except Exception:
        default_fmt = ""
    project = db.create_project(
        proj_title, format_mode=mode, narrative_engine=mode,
        default_writing_format=default_fmt,
    )
    scenes, block_to_scene = segment_blocks(doc)
    titles: list[str] = []
    scene_ids: list[int] = []   # scene_ids[ordinal] = the created scene's id
    for i, sc in enumerate(scenes, start=1):
        name = sc["title"] or f"Scene {i}"
        scene = db.create_scene(project.id, title=name, content=sc["content"])
        scene_ids.append(scene.id)
        titles.append(name)
    # Resolve each source block to the id of the scene it landed in (-1 if none).
    scene_ids_by_block = [
        scene_ids[o] if 0 <= o < len(scene_ids) else -1 for o in block_to_scene
    ]
    return {
        "project_id": project.id,
        "title": proj_title,
        "mode": mode,
        "scenes_created": len(titles),
        "scene_titles": titles,
        "scene_ids_by_block": scene_ids_by_block,
    }
