"""LLM branch evaluator — standardised critique-to-score via chat completion.

Returns factor scores (0–1) for each of the five scoring objectives.
Falls back to None on any LLM or parse failure so the caller can use
heuristic-only scoring.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from logosforge.assistant import chat_completion
from logosforge.providers import ProviderConfig

if TYPE_CHECKING:
    from logosforge.quantum_outliner.state import Branch

logger = logging.getLogger(__name__)

_TIMEOUT = 30

_SYSTEM_PROMPT = (
    "You are scoring narrative options. Return JSON only:\n"
    "{\n"
    '  "structure_fit": 0-1,\n'
    '  "psyke_consistency": 0-1,\n'
    '  "tension_gain": 0-1,\n'
    '  "novelty": 0-1,\n'
    '  "goal_alignment": 0-1\n'
    "}\n"
    "Criteria:\n"
    "- structure_fit: how well the option matches the current story beat/structure\n"
    "- psyke_consistency: how consistent with established characters, places, arcs\n"
    "- tension_gain: how much narrative tension this raises\n"
    "- novelty: how fresh and surprising this direction is\n"
    "- goal_alignment: how well this advances the protagonist's goals\n"
    "Return ONLY the JSON object. No markdown, no explanation."
)

_FACTOR_KEYS = frozenset({
    "structure_fit", "psyke_consistency", "tension_gain",
    "novelty", "goal_alignment",
})

_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _build_provider() -> ProviderConfig:
    # Delegates to the single shared provider builder (Phase 8B).
    from logosforge.providers import build_active_provider
    return build_active_provider()


def build_eval_prompt(
    branch: "Branch",
    *,
    beat: str | None = None,
    method: str | None = None,
    psyke_brief: str = "",
) -> str:
    """Build the structured user prompt for LLM evaluation."""
    sections: list[str] = []

    context_lines: list[str] = []
    if beat:
        context_lines.append(f"- Beat: {beat}")
    if method:
        context_lines.append(f"- Method: {method}")
    if psyke_brief:
        context_lines.append(f"- Story bible:\n{psyke_brief}")
    if context_lines:
        sections.append("Context:\n" + "\n".join(context_lines))

    option_lines = [f"Title: {branch.title}", f"Description: {branch.description}"]
    if branch.stakes:
        option_lines.append(f"Stakes: {branch.stakes}")
    if branch.consequence:
        option_lines.append(f"Consequence: {branch.consequence}")
    sections.append("Option:\n" + "\n".join(option_lines))

    return "\n\n".join(sections)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences wrapping JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _extract_json_object(text: str) -> str | None:
    """Find the first {...} substring in text."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _parse_factors(response: str) -> dict[str, float] | None:
    """Parse LLM response into factor dict. Returns None on any failure."""
    text = _strip_fences(response)

    extracted = _extract_json_object(text)
    if extracted is not None:
        text = extracted

    text = _TRAILING_COMMA.sub(r"\1", text)
    text = text.replace("'", '"')

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.debug("LLM evaluator returned invalid JSON: %s", text[:200])
        return None

    if not isinstance(data, dict):
        return None

    factors: dict[str, float] = {}
    for key in _FACTOR_KEYS:
        val = data.get(key)
        if val is None:
            return None
        try:
            f = float(val)
        except (TypeError, ValueError):
            return None
        factors[key] = max(0.0, min(f, 1.0))
    return factors


def score_with_llm(
    branch: "Branch",
    context: str = "",
    *,
    beat: str | None = None,
    method: str | None = None,
    psyke_brief: str = "",
    provider: ProviderConfig | None = None,
) -> dict[str, float] | None:
    """Call LLM to score a single branch. Returns None on any failure.

    Accepts either a plain *context* string (legacy) or structured keyword
    arguments (*beat*, *method*, *psyke_brief*).  Structured arguments are
    preferred; if none are provided the plain *context* string is used.
    """
    prov = provider or _build_provider()

    if beat or method or psyke_brief:
        user_msg = build_eval_prompt(
            branch, beat=beat, method=method, psyke_brief=psyke_brief,
        )
    elif context:
        user_msg = build_eval_prompt(branch)
        user_msg = f"Context:\n- {context}\n\n{user_msg}"
    else:
        user_msg = build_eval_prompt(branch)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    try:
        response, _ = chat_completion(
            messages, provider=prov, timeout=_TIMEOUT, use_cache=True,
        )
    except Exception:
        logger.debug("LLM evaluator call failed for branch %s", branch.id)
        return None
    return _parse_factors(response)


def evaluate_branches(
    branches: list["Branch"],
    context: str = "",
    *,
    beat: str | None = None,
    method: str | None = None,
    psyke_brief: str = "",
    provider: ProviderConfig | None = None,
) -> dict[str, dict[str, float]]:
    """Score multiple branches via LLM. Returns {branch_id: factors} for successes only."""
    prov = provider or _build_provider()
    results: dict[str, dict[str, float]] = {}
    for b in branches:
        factors = score_with_llm(
            b, context,
            beat=beat, method=method, psyke_brief=psyke_brief,
            provider=prov,
        )
        if factors is not None:
            results[b.id] = factors
    return results
