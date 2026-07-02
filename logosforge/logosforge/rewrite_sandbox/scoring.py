"""Deterministic rewrite variant scoring (Phase 10L). No LLM, no DB mutation."""

from __future__ import annotations

import re
from typing import Any

_WORD = re.compile(r"\w[\w'’\-]*", re.UNICODE)
_SENT = re.compile(r"[.!?]+")


def _words(t: str) -> int:
    return len(_WORD.findall(t or ""))


def _sentences(t: str) -> int:
    return max(1, len(_SENT.findall(t or "")))


def _paragraphs(t: str) -> int:
    return max(1, len([p for p in (t or "").split("\n\n") if p.strip()]))


def _dialogue_ratio(text: str) -> float:
    """Rough share of blocks that look like dialogue (screenplay-ish)."""
    try:
        from logosforge import screenplay_blocks as sb
        blocks = sb.parse_screenplay_text(text or "")
        if not blocks:
            return 0.0
        d = sum(1 for b in blocks if b.element_type == "dialogue")
        return round(d / len(blocks), 2)
    except Exception:
        return 0.0


def score_rewrite(db, project_id: int, source_text: str, variant_text: str, *,
                  writing_mode: str = "novel") -> dict[str, Any]:
    """Deterministic score comparing variant to source. Returns a JSON-able dict."""
    src, var = source_text or "", variant_text or ""
    sw, vw = _words(src), _words(var)
    length_delta = round((vw - sw) / sw, 3) if sw else (1.0 if vw else 0.0)

    score: dict[str, Any] = {
        "length_delta": length_delta,
        "source_words": sw, "variant_words": vw,
        "sentence_count_delta": _sentences(var) - _sentences(src),
        "paragraph_count_delta": _paragraphs(var) - _paragraphs(src),
        "estimated_reading_time_delta_min": round((vw - sw) / 200.0, 2),
        "dialogue_ratio_delta": round(_dialogue_ratio(var) - _dialogue_ratio(src), 2),
    }

    # PSYKE preservation (reuse the revision-intelligence detector).
    preserved = removed = added = 0
    try:
        from logosforge.revision_intelligence.psyke_impact import detect_psyke_impact
        impacts = detect_psyke_impact(db, project_id, src, var)
        for i in impacts:
            if i.impact_kind == "changed":
                preserved += 1
            elif i.impact_kind == "removed":
                removed += 1
            elif i.impact_kind == "added":
                added += 1
    except Exception:
        pass
    score["psyke_terms_preserved"] = preserved
    score["psyke_terms_removed"] = removed
    score["psyke_terms_added"] = added

    # Screenplay format warnings (deterministic).
    if (writing_mode or "") == "screenplay":
        warns = 0
        try:
            from logosforge import screenplay_blocks as sb
            blocks = sb.parse_screenplay_text(var)
            prev = None
            for b in blocks:
                if b.element_type == "dialogue" and prev not in (
                        "character", "parenthetical", "dialogue"):
                    warns += 1
                prev = b.element_type
        except Exception:
            pass
        score["screenplay_format_warnings"] = warns

    parts = []
    parts.append("shorter" if length_delta < -0.05 else
                 "longer" if length_delta > 0.05 else "similar length")
    if removed:
        parts.append(f"removes {removed} PSYKE reference(s)")
    if added:
        parts.append(f"adds {added} new reference(s)")
    score["summary"] = "Variant is " + ", ".join(parts) + "."
    return score
