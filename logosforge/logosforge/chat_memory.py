"""Chat memory and personality helpers for the project Chat section.

Pure-logic module — no Qt, no DB session management. The Database layer
calls these helpers to summarize old messages, build personality
prompts, and parse structured action proposals from LLM output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from logosforge.models.models import CHAT_PERSONALITIES


# ---------------------------------------------------------------------------
# Personality presets
# ---------------------------------------------------------------------------

_PERSONALITY_PROMPTS: dict[str, str] = {
    "default": (
        "You are a thoughtful writing collaborator for the user's story "
        "project. Be concise, specific, and grounded in the project's "
        "details when answering."
    ),
    "mentor": (
        "You are a patient, encouraging mentor. Ask clarifying questions, "
        "offer gentle redirects, and help the user think through choices "
        "rather than handing them solutions."
    ),
    "skeptic": (
        "You are a sharp skeptic. Push back on weak premises, name "
        "logical gaps, and never agree just to be agreeable. Be polite "
        "but unflinching."
    ),
    "editor": (
        "You are a senior fiction editor. Focus on clarity, pacing, "
        "characterization, and continuity. Be specific — quote lines "
        "and suggest concrete revisions."
    ),
    "brutal": (
        "You are a brutally honest critic. No flattery, no padding. "
        "If something doesn't work, say so plainly and explain why. "
        "If it does, say that briefly too."
    ),
    "whimsical": (
        "You are a playful, whimsical co-writer. Lean into metaphor, "
        "wordplay, and unexpected angles. Stay useful, but never dull."
    ),
    "minimalist": (
        "You are a minimalist. Use the fewest words that fully answer. "
        "Prefer lists and short sentences. Skip pleasantries."
    ),
    "philosopher": (
        "You are a literary philosopher. Treat narrative choices as "
        "questions about meaning. Connect specifics to broader themes "
        "without losing the concrete detail."
    ),
}


def personality_prompt(name: str) -> str:
    """Return the system-prompt fragment for a personality preset."""
    return _PERSONALITY_PROMPTS.get(name, _PERSONALITY_PROMPTS["default"])


def is_valid_personality(name: str) -> bool:
    return name in CHAT_PERSONALITIES


# ---------------------------------------------------------------------------
# Memory window + summarization
# ---------------------------------------------------------------------------

# Most recent N messages always sent verbatim.
RECENT_WINDOW = 12

# Once unsummarized count exceeds this, fold the older ones into the summary.
SUMMARIZE_THRESHOLD = 20


@dataclass(slots=True)
class MemoryFrame:
    """What gets sent to the LLM: a summary plus recent verbatim messages."""

    summary: str
    recent: list[dict]  # [{"role": ..., "content": ...}, ...]


def _to_role_dict(msg) -> dict:
    return {"role": msg.role, "content": msg.content}


def build_memory_frame(
    all_messages: list,
    summary_text: str,
    last_summarized_id: int,
) -> MemoryFrame:
    """Slice messages into (summary, recent) for the next LLM call.

    *all_messages* are in chronological order. The recent window is
    the last RECENT_WINDOW messages regardless of summary state — the
    summary covers everything older.
    """
    if not all_messages:
        return MemoryFrame(summary=summary_text, recent=[])
    recent = all_messages[-RECENT_WINDOW:]
    return MemoryFrame(
        summary=summary_text,
        recent=[_to_role_dict(m) for m in recent],
    )


def needs_summary_update(
    all_messages: list, last_summarized_id: int,
) -> bool:
    """True when there are enough older-than-recent messages to fold in."""
    if len(all_messages) <= RECENT_WINDOW:
        return False
    older = all_messages[:-RECENT_WINDOW]
    unsummarized = [m for m in older if m.id and m.id > last_summarized_id]
    return len(unsummarized) >= (SUMMARIZE_THRESHOLD - RECENT_WINDOW)


def heuristic_summary(
    previous_summary: str, new_messages: list,
) -> tuple[str, int]:
    """Append a terse heuristic summary line for *new_messages*.

    Returns (new_summary_text, last_message_id). This avoids a second
    LLM call — the summary just lists the topics covered. If the LLM
    is wired in later, replace this function's body; the caller
    contract stays the same.
    """
    if not new_messages:
        return previous_summary, 0
    bullets: list[str] = []
    for m in new_messages:
        text = m.content.strip().replace("\n", " ")
        if len(text) > 120:
            text = text[:117] + "..."
        bullets.append(f"- [{m.role}] {text}")
    new_block = "\n".join(bullets)
    if previous_summary:
        combined = previous_summary.rstrip() + "\n" + new_block
    else:
        combined = "Earlier conversation:\n" + new_block
    return combined, new_messages[-1].id or 0


# ---------------------------------------------------------------------------
# Action proposal parsing
# ---------------------------------------------------------------------------

# Openers for the two proposal formats. We locate the opener, then brace-match
# the JSON object that follows — this tolerates an omitted closing </action>
# (smaller models routinely drop it) and nested braces inside "args", neither
# of which a single regex handled.
_ACTION_OPEN_RE = re.compile(r"<action>", re.IGNORECASE)
_ACTION_CLOSE_RE = re.compile(r"\s*</action>", re.IGNORECASE)
_FENCE_OPEN_RE = re.compile(r"```(?:json)?", re.IGNORECASE)
_FENCE_CLOSE_RE = re.compile(r"\s*```")


@dataclass(slots=True)
class ActionProposal:
    """A structured action the assistant has proposed but not executed."""

    action: str
    args: dict
    label: str
    raw: str  # the original tag/fence so we can strip it from the visible text


def _find_json_object(text: str, start: int) -> tuple[str | None, int]:
    """Return ``(json_text, end_index)`` for the brace-balanced object at or
    after ``start``, honoring quoted strings and escapes, or ``(None, start)``
    when there is no complete object."""
    i = text.find("{", start)
    if i == -1:
        return None, start
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1], j + 1
    return None, start


def _action_spans(
    text: str,
    opener: re.Pattern,
    closer: re.Pattern,
    require_action_key: bool,
) -> list[tuple[int, int, str]]:
    """Locate proposal blocks for one format as ``(start, end, json_text)``.

    ``end`` includes the closing marker when present; when it's missing the
    span ends at the brace-matched JSON, so an unclosed proposal is still found
    (and later stripped) instead of leaking raw JSON into the chat.
    """
    spans: list[tuple[int, int, str]] = []
    consumed_to = 0
    for m in opener.finditer(text):
        if m.start() < consumed_to:
            # Opener lies inside a span we already took (e.g. the closing ```
            # of the previous fence) — don't re-open on it.
            continue
        json_text, jend = _find_json_object(text, m.end())
        if json_text is None:
            continue
        if require_action_key and '"action"' not in json_text:
            continue
        end = jend
        close = closer.match(text, jend)
        if close:
            end = close.end()
        spans.append((m.start(), end, json_text))
        consumed_to = end
    return spans


def parse_action_proposals(text: str) -> list[ActionProposal]:
    """Extract any ``<action>{...}</action>`` blocks from the LLM reply.

    Tolerant of an omitted closing ``</action>`` tag and of nested braces in
    ``args``. Falls back to a JSON code fence containing an ``"action"`` key
    when the explicit tag isn't used. Invalid JSON is silently ignored — the
    text still renders, just without an action card.
    """
    spans = _action_spans(text, _ACTION_OPEN_RE, _ACTION_CLOSE_RE, False)
    if not spans:
        spans = _action_spans(text, _FENCE_OPEN_RE, _FENCE_CLOSE_RE, True)

    proposals: list[ActionProposal] = []
    seen_raws: set[str] = set()
    for start, end, payload in spans:
        raw = text[start:end]
        if raw in seen_raws:
            continue
        seen_raws.add(raw)
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            continue
        proposal = _proposal_from_dict(data, raw)
        if proposal is not None:
            proposals.append(proposal)

    return proposals


def _proposal_from_dict(data: dict, raw: str) -> ActionProposal | None:
    action = data.get("action")
    if not isinstance(action, str) or not action:
        return None
    args = data.get("args", {})
    if not isinstance(args, dict):
        args = {}
    label = data.get("label") or _humanize_action(action)
    return ActionProposal(action=action, args=args, label=label, raw=raw)


def _humanize_action(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def strip_action_blocks(text: str) -> str:
    """Remove action tags/fences so the visible reply doesn't show JSON.

    Brace-matches the JSON object, so an unclosed ``<action>`` proposal is
    removed too instead of leaking raw JSON into the visible reply.
    """
    spans = (
        _action_spans(text, _ACTION_OPEN_RE, _ACTION_CLOSE_RE, False)
        + _action_spans(text, _FENCE_OPEN_RE, _FENCE_CLOSE_RE, True)
    )
    if not spans:
        return text.strip()

    spans.sort()
    out: list[str] = []
    last = 0
    for start, end, _ in spans:
        if start < last:  # overlapping span (shouldn't happen) — skip
            continue
        out.append(text[last:start])
        last = end
    out.append(text[last:])
    return "".join(out).strip()


def visible_reply_text(text: str, proposals: list[ActionProposal]) -> str:
    """The conversational text to show for an assistant turn.

    Strips action blocks from the raw reply. When the model answered with
    *only* an action block and no prose (common with smaller models), narrate
    the proposal so the conversation stays fluent instead of rendering an empty
    "(no response)" bubble.
    """
    visible = strip_action_blocks(text)
    if visible:
        return visible
    if proposals:
        if len(proposals) == 1:
            return (
                "I've prepared a change you can review below: "
                f"{proposals[0].label}."
            )
        return f"I've prepared {len(proposals)} changes you can review below."
    return "(no response)"


# ---------------------------------------------------------------------------
# System prompt assembly
# ---------------------------------------------------------------------------

_ACTIONS_HINT = (
    "When you want to perform a project change (create a scene, "
    "create a PSYKE entry, add a note, etc.), do NOT execute it "
    "yourself. Instead, propose it as a structured action the user "
    "can accept or decline. Format proposals as:\n"
    "<action>{\"action\": \"<name>\", \"args\": {...}, "
    "\"label\": \"<short label>\"}</action>\n"
    "Available write actions: create_scene, create_psyke_entry, "
    "create_note, update_scene_title.\n"
    "Always reply with a short, natural sentence to the user as well — "
    "never answer with only an action block. If the user just asked a "
    "question, answer it conversationally first and only propose an action "
    "when a project change is clearly wanted.\n"
    "Never produce destructive proposals (delete_*). The user must "
    "always confirm before any change is made."
)


def build_system_prompt(personality: str, project_context: str) -> str:
    """Assemble the system message: personality + context + action rules."""
    parts = [personality_prompt(personality)]
    if project_context.strip():
        parts.append("Project context:\n" + project_context.strip())
    parts.append(_ACTIONS_HINT)
    return "\n\n".join(parts)
