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

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from logosforge import writing_modes

_LOG = logging.getLogger(__name__)

# A screenplay scene break: a slug line (INT./EXT./EST./I/E) or a '.'-forced
# heading (a single leading dot, but not an ellipsis).
_SCENE_HEADING = re.compile(r"^\s*(INT|EXT|EST|INT\.?/EXT|I/E)[.\s]", re.IGNORECASE)
_FORCED_HEADING = re.compile(r"^\s*\.[^.\s]")
_MIN_CONTEXT_MATCH = 4
_MIN_ONE_SIDED = 8
_MAX_GAP_SLACK = 40


def _utf16_len(text: str) -> int:
    # Count JavaScript UTF-16 code units without encoding. ``surrogatepass``-like
    # handling matters here: a JS ``slice`` used for quote context can legally
    # leave one surrogate half at a 32-unit window boundary. That context is an
    # advisory locator and must not turn an otherwise valid bundle into a 500.
    return sum(2 if ord(char) > 0xFFFF else 1 for char in text)


def _has_surrogate_code_unit(text: str) -> bool:
    """Whether text contains a raw surrogate that SQLite/JSON cannot persist."""
    return any(0xD800 <= ord(char) <= 0xDFFF for char in text)


def _utf16_boundaries(text: str) -> list[int]:
    """UTF-16 offset at each Python character boundary."""
    offsets = [0]
    total = 0
    for char in text:
        total += _utf16_len(char)
        offsets.append(total)
    return offsets


def _python_index(text: str, utf16_offset: int) -> int | None:
    try:
        return _utf16_boundaries(text).index(utf16_offset)
    except ValueError:
        return None


def _slice_utf16(text: str, start: int, end: int) -> str | None:
    start_index = _python_index(text, start)
    end_index = _python_index(text, end)
    if start_index is None or end_index is None or end_index < start_index:
        return None
    return text[start_index:end_index]


@dataclass(frozen=True)
class _RenderedBlock:
    text: str
    # At a source boundary, a selection START belongs after opening/closing
    # formatting tokens while a selection END belongs before them. This keeps a
    # comment on the visible characters rather than on inserted markdown syntax.
    start_boundaries: dict[int, int]
    end_boundaries: dict[int, int]


@dataclass(frozen=True)
class _BlockPlacement:
    scene_index: int
    field: str
    start_boundaries: dict[int, int]
    end_boundaries: dict[int, int]


def _render_with_boundaries(
    text: str, marks: list[dict] | None, *, apply_marks: bool,
) -> _RenderedBlock:
    source_boundaries = _utf16_boundaries(text)
    source_to_python = {offset: index for index, offset in enumerate(source_boundaries)}
    opens: dict[int, list[str]] = {}
    closes: dict[int, list[str]] = {}
    if apply_marks:
        for mark in marks or []:
            if not isinstance(mark, dict):
                continue
            mark_type = str(mark.get("type", ""))
            try:
                start = int(mark.get("from", 0))
                end = int(mark.get("to", 0))
            except (TypeError, ValueError):
                continue
            start_index = source_to_python.get(start)
            end_index = source_to_python.get(end)
            if (
                mark_type not in ("bold", "italic")
                or start_index is None
                or end_index is None
                or start_index >= end_index
            ):
                continue
            token = "**" if mark_type == "bold" else "*"
            opens.setdefault(start_index, []).append(token)
            closes.setdefault(end_index, []).append(token)

    output: list[str] = []
    output_units = 0
    start_map: dict[int, int] = {}
    end_map: dict[int, int] = {}
    for index in range(len(text) + 1):
        source_offset = source_boundaries[index]
        end_map[source_offset] = output_units
        for token in closes.get(index, []):
            output.append(token)
            output_units += _utf16_len(token)
        for token in opens.get(index, []):
            output.append(token)
            output_units += _utf16_len(token)
        start_map[source_offset] = output_units
        if index < len(text):
            char = text[index]
            output.append(char)
            output_units += _utf16_len(char)
    return _RenderedBlock("".join(output), start_map, end_map)


def _apply_marks(text: str, marks: list[dict] | None) -> str:
    """Apply bold/italic ranges whose offsets use JavaScript UTF-16 units."""
    return _render_with_boundaries(text, marks, apply_marks=True).text


def _render_block(b: dict, apply_marks: bool) -> str:
    text = str(b.get("text", "") or "")
    return _render_with_boundaries(
        text, b.get("marks"), apply_marks=apply_marks,
    ).text


def _is_scene_break(b: dict, screenplay: bool) -> bool:
    if str(b.get("type", "")) == "heading":
        return True
    if screenplay:
        t = str(b.get("text", "") or "")
        return bool(_SCENE_HEADING.match(t) or _FORCED_HEADING.match(t))
    return False


def _adjust_boundaries(
    rendered: _RenderedBlock,
    *,
    base: int,
    retained_start: int,
    retained_end: int,
) -> tuple[dict[int, int], dict[int, int]]:
    def adjusted(mapping: dict[int, int]) -> dict[int, int]:
        result: dict[int, int] = {}
        for source_offset, relative in mapping.items():
            absolute = base + relative
            if retained_start <= absolute <= retained_end:
                result[source_offset] = absolute - retained_start
        return result

    return adjusted(rendered.start_boundaries), adjusted(rendered.end_boundaries)


def _segment_blocks_with_placements(
    doc: dict,
) -> tuple[list[dict[str, str]], list[int], dict[int, _BlockPlacement]]:
    """Internal segmentation plus exact source-block boundary maps."""
    mode = writing_modes.normalize_mode(str(doc.get("mode") or "novel"))
    blocks = doc.get("blocks") or []
    doc_title = str(doc.get("title") or "").strip() or "Untitled"
    screenplay = mode in ("screenplay", "series")
    apply_marks = not screenplay
    para_sep = "\n\n" if mode == "novel" else "\n"

    scenes: list[dict[str, str]] = []
    placements: dict[int, _BlockPlacement] = {}
    block_to_scene: list[int] = [-1] * len(blocks)
    cur_title: tuple[int, _RenderedBlock] | None = None
    # Screenplay slug lines serve two roles: they name the scene and remain in
    # its Fountain content. Keep their title text separately so the block's one
    # authoritative comment placement can stay in ``content``.
    cur_title_text: str | None = None
    cur_content: list[tuple[int, _RenderedBlock]] = []
    started = False

    def flush() -> None:
        nonlocal cur_title, cur_title_text, cur_content, started
        if not started:
            return
        scene_index = len(scenes)

        title_text = (
            cur_title[1].text if cur_title is not None else (cur_title_text or "")
        )
        stripped_title = title_text.strip()
        retained_title = stripped_title[:120]
        final_title = retained_title or doc_title or f"Scene {scene_index + 1}"

        raw_content = para_sep.join(rendered.text for _, rendered in cur_content)
        body = raw_content.strip()
        scenes.append({"title": final_title, "content": body})

        if cur_title is not None and retained_title:
            block_index, rendered = cur_title
            leading = _utf16_len(title_text) - _utf16_len(title_text.lstrip())
            retained_end = leading + _utf16_len(retained_title)
            start_map, end_map = _adjust_boundaries(
                rendered, base=0, retained_start=leading, retained_end=retained_end,
            )
            placements[block_index] = _BlockPlacement(
                scene_index, "title", start_map, end_map,
            )

        content_leading = _utf16_len(raw_content) - _utf16_len(raw_content.lstrip())
        content_end = content_leading + _utf16_len(body)
        base = 0
        separator_units = _utf16_len(para_sep)
        for position, (block_index, rendered) in enumerate(cur_content):
            start_map, end_map = _adjust_boundaries(
                rendered,
                base=base,
                retained_start=content_leading,
                retained_end=content_end,
            )
            placements[block_index] = _BlockPlacement(
                scene_index, "content", start_map, end_map,
            )
            base += _utf16_len(rendered.text)
            if position + 1 < len(cur_content):
                base += separator_units
        cur_title, cur_title_text, cur_content = None, None, []

    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            block_to_scene[index] = len(scenes) if started else -1
            continue
        text = str(block.get("text", "") or "")
        if _is_scene_break(block, screenplay):
            flush()
            started = True
            if str(block.get("type", "")) == "heading":
                cur_title = (
                    index,
                    _render_with_boundaries(text, None, apply_marks=False),
                )
                cur_title_text = None
            else:
                cur_title = None
                rendered_slug = _render_with_boundaries(
                    text, None, apply_marks=False,
                )
                cur_title_text = rendered_slug.text
                cur_content = [(index, rendered_slug)]
            block_to_scene[index] = len(scenes)
            continue

        started = True
        block_to_scene[index] = len(scenes)
        rendered = _render_with_boundaries(
            text, block.get("marks"), apply_marks=apply_marks,
        )
        if mode == "novel" and not rendered.text.strip():
            continue
        cur_content.append((index, rendered))
    flush()

    if not scenes:
        scenes.append({"title": doc_title, "content": ""})
    return scenes, block_to_scene, placements


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
    scenes, block_to_scene, _ = _segment_blocks_with_placements(doc)
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


def _common_prefix(left: str, right: str) -> int:
    count = 0
    for a, b in zip(left, right):
        if a != b:
            break
        count += 1
    return _utf16_len(left[:count])


def _common_suffix(left: str, right: str) -> int:
    return _common_prefix(left[::-1], right[::-1])


@dataclass(frozen=True)
class _Located:
    block_index: int
    from_offset: int
    to_offset: int


def _all_occurrences(text: str, needle: str) -> list[tuple[int, int, int]]:
    """Return ``(python_index, from_utf16, to_utf16)`` for every match."""
    if not needle:
        return []
    boundaries = _utf16_boundaries(text)
    matches: list[tuple[int, int, int]] = []
    start_at = 0
    while True:
        index = text.find(needle, start_at)
        if index < 0:
            return matches
        end_index = index + len(needle)
        matches.append((index, boundaries[index], boundaries[end_index]))
        start_at = index + 1


def _word_boundary_score(text: str, start: int, end: int) -> int:
    def is_word(char: str | None) -> bool:
        return char is not None and bool(re.match(r"\w", char))

    left = text[start - 1] if start > 0 else None
    right = text[end] if end < len(text) else None
    return int(not is_word(left)) + int(not is_word(right))


def _nearest(values: list[int], target: int) -> int:
    return min(values, key=lambda value: abs(value - target))


def _bracket_between(
    text: str,
    prefix: str,
    suffix: str,
    quote_length: int,
    hint_from: int,
    hint_to: int,
) -> tuple[int, int, int] | None:
    prefix_ends: list[int] = []
    prefix_score = 0
    for length in range(len(prefix), 0, -1):
        fragment = prefix[-length:]
        score = _utf16_len(fragment)
        if score < _MIN_CONTEXT_MATCH:
            break
        occurrences = _all_occurrences(text, fragment)
        if occurrences:
            prefix_ends = [end for _, _, end in occurrences]
            prefix_score = score
            break

    suffix_starts: list[int] = []
    suffix_score = 0
    for length in range(len(suffix), 0, -1):
        fragment = suffix[:length]
        score = _utf16_len(fragment)
        if score < _MIN_CONTEXT_MATCH:
            break
        occurrences = _all_occurrences(text, fragment)
        if occurrences:
            suffix_starts = [start for _, start, _ in occurrences]
            suffix_score = score
            break

    pairs = [
        (
            abs(prefix_end - hint_from) + abs(suffix_start - hint_to),
            prefix_end,
            suffix_start,
        )
        for prefix_end in prefix_ends
        for suffix_start in suffix_starts
        if suffix_start >= prefix_end
        and suffix_start - prefix_end <= quote_length + _MAX_GAP_SLACK
    ]
    if pairs:
        _, start, end = min(pairs)
        return start, end, prefix_score + suffix_score
    if prefix_ends and prefix_score >= _MIN_ONE_SIDED:
        start = _nearest(prefix_ends, hint_from)
        return start, min(start + quote_length, _utf16_len(text)), prefix_score
    if suffix_starts and suffix_score >= _MIN_ONE_SIDED:
        end = _nearest(suffix_starts, hint_to)
        return max(0, end - quote_length), end, suffix_score
    return None


def _locate_source_span(
    texts: list[str | None],
    quote: str,
    hint_block: int,
    hint_from: int,
    prefix: str,
    suffix: str,
) -> _Located | None:
    """Port Whiteboard's TextQuote relocation using explicit UTF-16 units."""
    if not quote:
        if not (0 <= hint_block < len(texts)) or texts[hint_block] is None:
            return None
        if _python_index(texts[hint_block] or "", hint_from) is None:
            return None
        return _Located(hint_block, hint_from, hint_from)

    quote_length = _utf16_len(quote)
    hint_to = hint_from + quote_length
    if 0 <= hint_block < len(texts) and texts[hint_block] is not None:
        stored = texts[hint_block] or ""
        if _slice_utf16(stored, hint_from, hint_to) == quote:
            before = _context_before(stored, hint_from, _utf16_len(prefix))
            after = _context_after(stored, hint_to, _utf16_len(suffix))
            score = _common_suffix(prefix, before) + _common_prefix(suffix, after)
            if (not prefix and not suffix) or score >= _MIN_CONTEXT_MATCH:
                return _Located(hint_block, hint_from, hint_to)

    # Exact quote anywhere: context, then word boundaries, then proximity.
    candidates: list[tuple[int, int, int, int, int, int]] = []
    for block_index, text in enumerate(texts):
        if text is None:
            continue
        for python_start, start, end in _all_occurrences(text, quote):
            python_end = python_start + len(quote)
            before = _context_before(text, start, _utf16_len(prefix))
            after = _context_after(text, end, _utf16_len(suffix))
            score = _common_suffix(prefix, before) + _common_prefix(suffix, after)
            word_score = _word_boundary_score(text, python_start, python_end)
            distance = abs(block_index - hint_block) * 100000 + abs(start - hint_from)
            candidates.append(
                (-score, -word_score, distance, block_index, start, end),
            )
    if candidates:
        _, _, _, block_index, start, end = min(candidates)
        return _Located(block_index, start, end)

    # The quote itself changed: bracket the replacement between surviving
    # context landmarks, exactly as Whiteboard does.
    if (
        _utf16_len(prefix) >= _MIN_CONTEXT_MATCH
        or _utf16_len(suffix) >= _MIN_CONTEXT_MATCH
    ):
        brackets: list[tuple[int, int, int, int, int, int]] = []
        for block_index, text in enumerate(texts):
            if text is None:
                continue
            bracket = _bracket_between(
                text, prefix, suffix, quote_length, hint_from, hint_to,
            )
            if bracket is None:
                continue
            start, end, score = bracket
            distance = abs(block_index - hint_block) * 100000 + abs(start - hint_from)
            brackets.append((-score, distance, block_index, start, end, score))
        if brackets:
            _, _, block_index, start, end, _ = min(brackets)
            return _Located(block_index, start, end)
    return None


def _resolve_source_location(
    comment: dict, blocks: list, start_index: int, end_index: int,
) -> tuple[_Located, _Located] | None:
    anchor = comment.get("anchor")
    if not isinstance(anchor, dict):
        return None
    quote = str(comment.get("quote") or "")
    if not quote:
        return None
    try:
        hint_from = int(anchor.get("from_offset", 0))
        hint_to = int(anchor.get("to_offset", 0))
    except (TypeError, ValueError):
        return None
    texts: list[str | None] = [
        str(block.get("text", "") or "") if isinstance(block, dict) else None
        for block in blocks
    ]
    prefix = str(anchor.get("prefix") or "")
    suffix = str(anchor.get("suffix") or "")
    if start_index == end_index:
        located = _locate_source_span(
            texts, quote, start_index, hint_from, prefix, suffix,
        )
        return (located, located) if located is not None else None

    quote_parts = quote.split("\n")
    if len(quote_parts) < 2:
        return None
    first, last = quote_parts[0], quote_parts[-1]
    if first:
        start = _locate_source_span(
            texts,
            first,
            start_index,
            hint_from,
            prefix,
            "",
        )
    else:
        start = _locate_source_span(
            texts, "", start_index, hint_from, prefix, "",
        )
    if last:
        end = _locate_source_span(
            texts, last, end_index, 0, "", suffix,
        )
    else:
        end = _locate_source_span(texts, "", end_index, hint_to, "", suffix)
    if start is not None and end is not None and end.block_index >= start.block_index:
        return start, end
    # Match Whiteboard's edge-survival rule: when one side of a multi-block
    # selection disappeared, retain the thread on the surviving edge.
    if start is not None:
        return start, start
    if end is not None:
        return end, end
    return None


def _resolve_block_index(
    blocks: list,
    indexes_by_id: dict[str, list[int]],
    index_value: object,
    block_id: object,
) -> int | None:
    stable_id = str(block_id or "").strip()
    matches = indexes_by_id.get(stable_id, []) if stable_id else []
    if len(matches) == 1:
        return matches[0]
    try:
        index = int(index_value)
    except (TypeError, ValueError):
        return None
    # A stale legacy hint may point outside the current list. Keep it as a
    # proximity hint: TextQuote relocation can still find the selection in a
    # surviving block.
    return index


def _context_before(text: str, offset: int, limit: int = 32) -> str:
    index = _python_index(text, offset)
    if index is None:
        return ""
    result = text[:index]
    while result and _utf16_len(result) > limit:
        result = result[1:]
    return result


def _context_after(text: str, offset: int, limit: int = 32) -> str:
    index = _python_index(text, offset)
    if index is None:
        return ""
    result = text[index:]
    while result and _utf16_len(result) > limit:
        result = result[:-1]
    return result


def _map_comment_anchor(
    comment: dict,
    blocks: list,
    scenes: list[dict[str, str]],
    placements: dict[int, _BlockPlacement],
    scene_ids: list[int],
) -> dict | None:
    anchor = comment.get("anchor")
    if not isinstance(anchor, dict):
        return None
    indexes_by_id: dict[str, list[int]] = {}
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("id") or "").strip()
        if block_id:
            indexes_by_id.setdefault(block_id, []).append(index)
    start_index = _resolve_block_index(
        blocks, indexes_by_id, anchor.get("block_index"), anchor.get("block_id"),
    )
    end_index_value = anchor.get("end_block_index")
    has_explicit_end_index = end_index_value is not None
    if not has_explicit_end_index:
        end_index_value = anchor.get("block_index")
    end_block_id = anchor.get("end_block_id")
    # A missing end id means "same block" only for a single-block anchor.
    # Older/transitional bundles may carry a valid explicit end index without
    # the newer stable end id; substituting the start id would collapse that
    # range back onto its first block and silently skip the thread.
    if not end_block_id and not has_explicit_end_index:
        end_block_id = anchor.get("block_id")
    end_index = _resolve_block_index(
        blocks,
        indexes_by_id,
        end_index_value,
        end_block_id,
    )
    if start_index is None or end_index is None:
        return None
    source_location = _resolve_source_location(
        comment, blocks, start_index, end_index,
    )
    if source_location is None:
        return None
    start_location, end_location = source_location
    start_placement = placements.get(start_location.block_index)
    end_placement = placements.get(end_location.block_index)
    if start_placement is None or end_placement is None:
        return None
    from_offset = start_placement.start_boundaries.get(start_location.from_offset)
    to_offset = end_placement.end_boundaries.get(end_location.to_offset)
    if from_offset is None or to_offset is None:
        return None
    start_key = (
        start_placement.scene_index,
        0 if start_placement.field == "title" else 1,
    )
    end_key = (
        end_placement.scene_index,
        0 if end_placement.field == "title" else 1,
    )
    if start_key > end_key or (start_key == end_key and to_offset < from_offset):
        return None
    start_text = scenes[start_placement.scene_index][start_placement.field]
    end_text = scenes[end_placement.scene_index][end_placement.field]
    quote = str(comment.get("quote") or "")
    if start_key == end_key:
        quote = _slice_utf16(start_text, from_offset, to_offset) or quote
    return {
        "start_scene_id": scene_ids[start_placement.scene_index],
        "start_field": start_placement.field,
        "from_offset": from_offset,
        "end_scene_id": scene_ids[end_placement.scene_index],
        "end_field": end_placement.field,
        "to_offset": to_offset,
        "prefix": _context_before(start_text, from_offset),
        "suffix": _context_after(end_text, to_offset),
        "quote": quote,
    }


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and value.strip():
        try:
            result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def import_whiteboard_document(
    db, doc: dict, *, title: str | None = None,
) -> dict[str, Any]:
    """Create a NEW project from a whiteboard document and populate its scenes.

    Returns ``{project_id, title, mode, scenes_created, scene_titles}``. The new
    project's writing mode matches the document's ``mode`` so the core's format
    intelligence + export work immediately.
    """
    mode = writing_modes.normalize_mode(str(doc.get("mode") or "novel"))
    proj_title = (
        title
        or str(doc.get("title") or "").strip()
        or "Imported from Whiteboard"
    )
    try:
        default_fmt = writing_modes.default_writing_format(mode)
    except Exception:
        default_fmt = ""
    project = db.create_project(
        proj_title, format_mode=mode, narrative_engine=mode,
        default_writing_format=default_fmt,
    )
    try:
        scenes, block_to_scene, placements = _segment_blocks_with_placements(doc)
        titles: list[str] = []
        scene_ids: list[int] = []   # scene_ids[ordinal] = the created scene's id
        for i, sc in enumerate(scenes, start=1):
            name = sc["title"] or f"Scene {i}"
            scene = db.create_scene(project.id, title=name, content=sc["content"])
            scene_ids.append(scene.id)
            titles.append(name)

        comments_created = 0
        comments_skipped = 0
        comment_replies_created = 0
        comment_replies_skipped = 0
        blocks = doc.get("blocks") or []
        source_comments = doc.get("comments") or []
        if not isinstance(source_comments, list):
            source_comments = []
        for source_comment in source_comments:
            if not isinstance(source_comment, dict):
                comments_skipped += 1
                continue
            raw_replies = source_comment.get("replies") or []
            if not isinstance(raw_replies, list):
                raw_replies = []
            mapped = _map_comment_anchor(
                source_comment, blocks, scenes, placements, scene_ids,
            )
            source_id = str(source_comment.get("id") or "").strip()
            source_body = str(source_comment.get("body") or "")
            if (
                mapped is None
                or not source_id
                or _has_surrogate_code_unit(source_id)
                or _has_surrogate_code_unit(source_body)
                or _has_surrogate_code_unit(str(mapped.get("quote") or ""))
            ):
                comments_skipped += 1
                comment_replies_skipped += len(raw_replies)
                continue

            replies: list[dict] = []
            for order, source_reply in enumerate(raw_replies):
                if not isinstance(source_reply, dict):
                    comment_replies_skipped += 1
                    continue
                reply_source_id = str(source_reply.get("id") or "").strip()
                reply_body = str(source_reply.get("body") or "")
                reply_author = str(source_reply.get("author") or "you")
                if (
                    not reply_source_id
                    or _has_surrogate_code_unit(reply_source_id)
                    or _has_surrogate_code_unit(reply_body)
                    or _has_surrogate_code_unit(reply_author)
                ):
                    comment_replies_skipped += 1
                    continue
                replies.append({
                    "source_id": reply_source_id,
                    "body": reply_body,
                    "author": reply_author,
                    "sort_order": order,
                    "created_at": _coerce_datetime(source_reply.get("created_at")),
                })

            created_at = _coerce_datetime(source_comment.get("created_at"))
            updated_at = _coerce_datetime(source_comment.get("updated_at"))
            db.create_comment_with_replies(
                project.id,
                source_id=source_id,
                start_scene_id=mapped["start_scene_id"],
                start_field=mapped["start_field"],
                from_offset=mapped["from_offset"],
                end_scene_id=mapped["end_scene_id"],
                end_field=mapped["end_field"],
                to_offset=mapped["to_offset"],
                quote=mapped["quote"],
                prefix=mapped["prefix"],
                suffix=mapped["suffix"],
                body=source_body,
                resolved=bool(source_comment.get("resolved", False)),
                replies=replies,
                created_at=created_at,
                updated_at=updated_at,
            )
            comments_created += 1
            comment_replies_created += len(replies)
    except Exception:
        # Database helpers commit per operation. Compensate as one logical import:
        # never leave a project containing only the scenes created before a later
        # failure. Preserve the original exception if cleanup itself has trouble.
        try:
            db.delete_project(project.id)
        except Exception:
            _LOG.exception(
                "Could not roll back failed Whiteboard import project %s",
                project.id,
            )
        raise
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
        "comments_created": comments_created,
        "comments_skipped": comments_skipped,
        "comment_replies_created": comment_replies_created,
        "comment_replies_skipped": comment_replies_skipped,
    }
