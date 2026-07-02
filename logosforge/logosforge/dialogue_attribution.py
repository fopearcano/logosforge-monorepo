"""Dialogue speaker attribution — maps quoted spans to characters.

Detects dialogue in prose text and infers which character is speaking
using speech-tag matching, proximity heuristics, and turn-taking
continuity.  Falls back to ``None`` when the speaker cannot be resolved.

Primary API: ``attribute_dialogue(text, characters)``
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class DialogueSegment:
    text: str
    start_pos: int
    end_pos: int
    speaker_id: int | None


_SPEECH_VERBS = (
    "said|asked|replied|whispered|shouted|muttered|snapped|"
    "snarled|growled|called|screamed|yelled|cried|exclaimed|"
    "demanded|pleaded|groaned|sighed|murmured|hissed|barked|"
    "stammered|declared|announced|added|continued|insisted|"
    "answered|responded|warned|promised|threatened|mocked|"
    "suggested|agreed|protested|urged|scoffed|laughed"
)

_QUOTE_RE = re.compile(
    r'["“]([^"“”]*)["”]'
    r"|"
    r"['‘]([^'‘’]*)['’]",
)

def _build_name_index(
    characters: list,
) -> dict[str, int]:
    """Map lowercase character names (and first-name tokens) to IDs."""
    index: dict[str, int] = {}
    for ch in characters:
        name: str = ch.name
        lower = name.lower()
        index[lower] = ch.id
        parts = name.split()
        if len(parts) > 1:
            index[parts[0].lower()] = ch.id
    return index


_SENT_BREAK_RE = re.compile(r"[.!?]\s|\n")


def _search_tag(
    text: str,
    start: int,
    end: int,
    name_index: dict[str, int],
    prev_end: int,
    next_start: int,
) -> int | None:
    """Look for 'Name verb' or 'verb Name' in the gaps around this quote.

    Only searches within the same sentence — sentence boundaries (period,
    newline, etc.) cut off the search so tags aren't mis-assigned to the
    wrong quote.
    """
    before = text[prev_end:start]
    after = text[end:next_start]

    breaks = list(_SENT_BREAK_RE.finditer(before))
    before_clip = before[breaks[-1].end():] if breaks else before

    m_break = _SENT_BREAK_RE.search(after)
    after_clip = after[:m_break.start()] if m_break else after

    patterns = []
    for name, cid in name_index.items():
        patterns.append((cid, rf"(?i)\b{re.escape(name)}\s+(?:{_SPEECH_VERBS})\b"))
        patterns.append((cid, rf"(?i)\b(?:{_SPEECH_VERBS})\s+{re.escape(name)}\b"))

    for region in (before_clip, after_clip):
        for cid, pat in patterns:
            if re.search(pat, region):
                return cid

    return None


def _search_proximity(
    text: str,
    start: int,
    end: int,
    name_index: dict[str, int],
) -> int | None:
    """Check if a character name appears on the same line as the quote."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].lower()

    quote_lower = text[start:end].lower()
    outside = line.replace(quote_lower, "", 1)

    for name, cid in name_index.items():
        if re.search(rf"\b{re.escape(name)}\b", outside):
            return cid
    return None


def attribute_dialogue(
    text: str,
    characters: list,
) -> list[DialogueSegment]:
    """Return attributed dialogue segments found in *text*.

    *characters* is a sequence of objects with ``.id`` (int) and
    ``.name`` (str) attributes — typically ``Character`` model instances.
    """
    if not text or not characters:
        return []

    name_index = _build_name_index(characters)
    matches = list(_QUOTE_RE.finditer(text))
    if not matches:
        return []

    segments: list[DialogueSegment] = []
    prev_speakers: list[int] = []

    for i, m in enumerate(matches):
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        start, end = m.start(), m.end()

        prev_end = matches[i - 1].end() if i > 0 else 0
        next_start = matches[i + 1].start() if i < len(matches) - 1 else len(text)

        speaker = _search_tag(text, start, end, name_index, prev_end, next_start)

        if speaker is None:
            speaker = _search_proximity(text, start, end, name_index)

        if speaker is None and len(prev_speakers) >= 2:
            last = prev_speakers[-1]
            second_last = prev_speakers[-2]
            if last != second_last:
                speaker = second_last

        segments.append(DialogueSegment(
            text=inner,
            start_pos=start,
            end_pos=end,
            speaker_id=speaker,
        ))

        if speaker is not None:
            prev_speakers.append(speaker)

    return segments
