"""Logos prompt builder — an adapter over the existing Assistant context system.

This module turns a (LogosContext, LogosAction) pair into the message list the
shared Assistant backend expects. It deliberately does NOT build its own context
system: it calls the existing ``logosforge.context_builder`` gatherers and the
existing ``logosforge.assistant.build_messages``.

It keeps the prompt focused (selected text / node + only the relevant context
slices) and never logs or includes secrets/API keys.
"""

from __future__ import annotations

from collections.abc import Callable

from logosforge.logos.actions import LogosAction
from logosforge.logos.context import LogosContext

LOGOS_SYSTEM_PROMPT = (
    "You are Logos, an inline, contextual writing companion embedded next to "
    "the author's work. You give concise, concrete, non-destructive guidance "
    "for the current selection or outline node. You never silently rewrite or "
    "replace the author's text; any alternate versions you show are clearly "
    "labelled options. Respond in the same language as the author's text. "
    "Use any reference context you are given only to inform your reply — never "
    "repeat, quote, or summarise it, and never echo internal grounding labels "
    "such as \"[PSYKE Context]\", \"Global Story Memory\" or \"[AI Mode: ...]\". "
    "Skip throat-clearing preambles like \"Here is the rewrite:\". When the action "
    "asks you to label options or a version (e.g. \"Option 1:\", \"Expanded "
    "version:\"), use exactly those labels; otherwise reply with the content itself."
)

# Cap how much selected text we forward, so prompts stay focused.
_SELECTION_LIMIT = 4000


def gather_context_strings(db, ctx: LogosContext) -> dict[str, str]:
    """Reuse the shared context builders (read-only) — no DB re-querying logic
    of our own. Returns the context slices relevant to *ctx*'s section."""
    from logosforge import context_builder as cb

    out = {
        "scene_context": "",
        "outline_context": "",
        "psyke_context": "",
        "notes_context": "",
    }
    pid = ctx.project_id
    query = ctx.selected_text or ctx.outline_node_label or ctx.cursor_text_excerpt

    if ctx.current_scene_id is not None:
        out["scene_context"] = _safe(cb.gather_scene_context, db, pid, ctx.current_scene_id)
    # Outline structure (parent/child beats) matters for the Outline section.
    if ctx.section_name == "Outline" or ctx.current_scene_id is not None:
        out["outline_context"] = _safe(cb.gather_outline_context, db, pid)
    out["psyke_context"] = _safe(cb.gather_psyke_context, db, pid, ctx.current_scene_id, query)
    out["notes_context"] = _safe(cb.gather_notes_context, db, pid, ctx.current_scene_id, query)
    return out


def build_action_prompt(ctx: LogosContext, action: LogosAction) -> str:
    """The task-specific user prompt: action instruction + the focal material."""
    parts: list[str] = [action.prompt]

    sel = (ctx.selected_text or "").strip()
    if sel:
        parts.append(f"Selected text:\n\"\"\"\n{sel[:_SELECTION_LIMIT]}\n\"\"\"")
    elif ctx.cursor_text_excerpt.strip():
        parts.append(f"Nearby text:\n\"\"\"\n{ctx.cursor_text_excerpt.strip()}\n\"\"\"")

    if ctx.outline_node_label:
        kind = ctx.outline_node_kind or "node"
        parts.append(f"Selected outline node ({kind}): {ctx.outline_node_label}")

    meta: list[str] = []
    if ctx.narrative_engine:
        meta.append(f"narrative engine: {ctx.narrative_engine}")
    if ctx.writing_format:
        meta.append(f"writing format: {ctx.writing_format}")
    if ctx.outline_template:
        meta.append(f"outline template: {ctx.outline_template}")
    if ctx.section_name:
        meta.append(f"section: {ctx.section_name}")
    if meta:
        parts.append("(" + "; ".join(meta) + ")")

    return "\n\n".join(parts)


def build_logos_messages(db, ctx: LogosContext, action: LogosAction) -> list[dict]:
    """Assemble the chat messages via the shared ``assistant.build_messages``."""
    from logosforge.assistant import build_messages

    ctx_strings = gather_context_strings(db, ctx)
    return build_messages(
        action_prompt=build_action_prompt(ctx, action),
        scene_context=ctx_strings["scene_context"],
        outline_context=ctx_strings["outline_context"],
        psyke_context=ctx_strings["psyke_context"],
        notes_context=ctx_strings["notes_context"],
        system_prompt=LOGOS_SYSTEM_PROMPT,
    )


def _safe(fn: Callable, *args) -> str:
    try:
        return fn(*args) or ""
    except Exception:
        return ""
