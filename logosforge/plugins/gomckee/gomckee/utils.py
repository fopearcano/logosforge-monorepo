from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Set


_WORD_RE = re.compile(r"[a-z0-9']+")


def normalize_text(text: str) -> str:
    return " ".join(_WORD_RE.findall((text or "").lower()))


def tokenize(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def keyword_score(tokens: Sequence[str], phrases: Iterable[str]) -> int:
    token_set: Set[str] = set(tokens)
    normalized = " ".join(tokens)
    score = 0
    for phrase in phrases:
        phrase = phrase.strip().lower()
        if not phrase:
            continue
        parts = phrase.split()
        if len(parts) == 1:
            score += 1 if parts[0] in token_set else 0
        else:
            score += 1 if phrase in normalized else 0
    return score


def ensure_list(value):
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]
