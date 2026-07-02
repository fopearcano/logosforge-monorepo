"""Lightweight writing analytics — heuristic metrics for scene text."""

SENTENCE_ENDINGS = frozenset(".!?")
QUOTE_CHARS = frozenset('""\u201c\u201d')


def compute_scene_stats(text: str) -> dict:
    """Return word, paragraph, sentence, and dialogue metrics for *text*."""
    if not text or not text.strip():
        return {
            "words": 0,
            "paragraphs": 0,
            "sentences": 0,
            "dialogue_ratio": 0.0,
            "hint": "",
        }

    words = len(text.split())
    paragraphs = len([p for p in text.split("\n\n") if p.strip()])
    sentences = sum(1 for ch in text if ch in SENTENCE_ENDINGS)
    if sentences == 0 and words > 0:
        sentences = 1

    non_empty_lines = [ln for ln in text.splitlines() if ln.strip()]
    total_lines = len(non_empty_lines)
    if total_lines > 0:
        dialogue_lines = sum(
            1 for ln in non_empty_lines
            if any(ch in ln for ch in QUOTE_CHARS)
        )
        dialogue_ratio = dialogue_lines / total_lines
    else:
        dialogue_ratio = 0.0

    hint = _classify(words, dialogue_ratio)

    return {
        "words": words,
        "paragraphs": paragraphs,
        "sentences": sentences,
        "dialogue_ratio": dialogue_ratio,
        "hint": hint,
    }


def _classify(words: int, dialogue_ratio: float) -> str:
    parts: list[str] = []
    if words < 200:
        parts.append("short")
    elif words > 2000:
        parts.append("long")
    if dialogue_ratio > 0.5:
        parts.append("dialogue-heavy")
    elif dialogue_ratio < 0.1 and words > 50:
        parts.append("narrative-heavy")
    return ", ".join(parts)


def compute_project_stats(scene_texts: list[str]) -> dict:
    """Return aggregate stats across all scenes."""
    if not scene_texts:
        return {
            "scene_count": 0,
            "avg_words": 0,
            "longest": 0,
            "shortest": 0,
        }

    counts = [len(t.split()) for t in scene_texts if t and t.strip()]
    if not counts:
        return {
            "scene_count": len(scene_texts),
            "avg_words": 0,
            "longest": 0,
            "shortest": 0,
        }

    return {
        "scene_count": len(scene_texts),
        "avg_words": sum(counts) // len(counts),
        "longest": max(counts),
        "shortest": min(counts),
    }
