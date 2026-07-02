"""LittleBoy — Whiteboard Small AI: Billy (chat) + Logos (inline).

Ports the standalone backend's PROMPT orchestration (Billy system prompt, the
ten Logos action templates, suggested_replacement extraction, placeholders) but
delegates the actual LLM round-trip to the CORE's project-scoped
``assistant/chat`` — which resolves the provider via the core's
``build_active_provider()`` and settings. So the wrapper owns *presentation /
prompt* logic; the core owns *behavior / transport*. When the core has no
provider configured (or it errors) the core returns 502 and we degrade to a
clearly-labelled placeholder — stable API shape either way. ``connect_to_psyke``
uses the core PSYKE search, not the LLM.

This is the Small system only: no Counterpart, no Quantum, no multi-agent.
"""
from __future__ import annotations

import re
import uuid
from typing import List, Optional

import httpx
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.core_client import resolve_pid

router = APIRouter()

# Map the Whiteboard frontend's Logos vocabulary onto the core Logos action
# registry (logosforge.logos.actions, section "Inline"). This is pure DTO
# translation — the action behavior (prompts, transform-vs-diagnostic split, the
# connect-to-PSYKE heuristic) now lives in the CORE, consumed via /logos/run.
_CORE_ACTION: dict[str, str] = {
    "suggest": "inline_suggest",
    "rewrite": "inline_rewrite",
    "expand": "inline_expand",
    "compress": "inline_compress",
    "explain": "inline_explain",
    "improve_dialogue": "inline_improve_dialogue",
    "improve_action": "inline_improve_action",
    "make_more_visual": "inline_make_visual",
    "summarize": "inline_summarize",
    "connect_to_psyke": "connect_to_psyke",
}

_NO_PROVIDER_NOTE = (
    "Placeholder — configure an AI provider in LogosForge "
    "(ai_provider / ai_model / ai_base_url) to enable real AI."
)


# -- DTOs (mirror the frontend littleboy contract) ---------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class BillyChatRequest(BaseModel):
    message: str
    selected_text: Optional[str] = None
    nearby_context: Optional[str] = None
    writing_mode: Optional[str] = None
    document_title: Optional[str] = None
    conversation_id: Optional[str] = None
    history: Optional[List[ChatMessage]] = None


class BillyChatResponse(BaseModel):
    ok: bool
    conversation_id: str
    message: ChatMessage
    provider: str
    note: Optional[str] = None


class LogosRequest(BaseModel):
    action: Optional[str] = "rewrite"
    selected_text: Optional[str] = None
    nearby_context: Optional[str] = None
    writing_mode: Optional[str] = None
    instruction: Optional[str] = None
    document_title: Optional[str] = None


class LogosResponse(BaseModel):
    ok: bool
    action: str
    result: str
    suggested_replacement: Optional[str] = None
    provider: str
    note: Optional[str] = None


# -- core delegation ---------------------------------------------------------

async def _core_chat(core, pid: int, system_prompt: str, message: str,
                     history: Optional[List[ChatMessage]] = None, *,
                     selected_text: str = "", nearby_text: str = "",
                     document_title: str = "") -> str:
    """Round-trip through the core assistant/chat. Editor context (selection /
    nearby text / document title) is passed as fields so the CORE folds it into
    its grounding — the wrapper never hand-builds a context preamble. Raises
    HTTPStatusError (502) when the core has no provider / the provider errors."""
    body = {
        "message": message,
        "system_prompt": system_prompt,
        "history": [{"role": m.role, "content": m.content} for m in (history or [])],
        "selected_text": selected_text,
        "nearby_text": nearby_text,
        "document_title": document_title,
    }
    r = await core.request("POST", f"/api/projects/{pid}/assistant/chat", json=body)
    return r.json().get("reply", "")


async def _provider_name(core, pid: int) -> str:
    try:
        s = (await core.request("GET", f"/api/projects/{pid}/assistant/settings")).json()
        return s.get("provider") or "logosforge"
    except Exception:
        return "logosforge"


def _comments_context(pid: int) -> str:
    """Fold the writer's margin comments into a context block so the assistants are
    comment-aware. OPEN notes are live requests to take into account; RESOLVED notes
    record decisions the writer already settled (surfaced so the AI respects them
    and doesn't reopen them). Read straight from the per-document store."""
    try:
        from app.local_state import comments_store
        notes = [c for c in comments_store.get(str(pid)).comments if (c.body or "").strip()]
    except Exception:
        return ""
    if not notes:
        return ""

    def _line(c) -> str:
        head = f'- On "{(c.quote or "").strip()[:80]}": {c.body.strip()}'
        replies = getattr(c, "replies", None) or []
        thread = "; ".join(
            f'{(r.author or "you")}: {(r.body or "").strip()}'
            for r in replies
            if (r.body or "").strip()
        )
        return f"{head}  (thread — {thread})" if thread else head

    open_notes = [c for c in notes if not c.resolved][:30]
    resolved_notes = [c for c in notes if c.resolved][:15]
    parts: list[str] = []
    if open_notes:
        parts.append(
            "The writer left these OPEN margin comments on the text (take them into account):\n"
            + "\n".join(_line(c) for c in open_notes)
        )
    if resolved_notes:
        parts.append(
            "These margin comments are already RESOLVED — decisions the writer settled; "
            "respect them and don't reopen them:\n"
            + "\n".join(_line(c) for c in resolved_notes)
        )
    return "\n\n".join(parts)


# -- @-mention → AI reply in a comment thread --------------------------------

_MENTION_RE = re.compile(r"@(billy|logos)\b", re.IGNORECASE)


def _detect_mention(text: str) -> Optional[str]:
    """Return the @-mentioned assistant name ("Billy"/"Logos"), or None."""
    m = _MENTION_RE.search(text or "")
    return m.group(1).capitalize() if m else None


async def ai_reply_to_comment(core, pid: int, assistant: str, comment) -> str:
    """Generate a brief assistant reply to a comment thread (the writer @-mentioned
    it). Degrades to a clearly-labelled note when no AI provider is configured."""
    quote = (comment.quote or "").strip()
    thread = "\n".join(
        f"{r.author}: {(r.body or '').strip()}"
        for r in (comment.replies or [])
        if (r.body or "").strip()
    )
    system = (
        f"You are {assistant}, a concise, friendly writing assistant embedded in a margin-comment "
        "thread in the LogosForge Whiteboard. The writer @-mentioned you in a comment about a "
        "passage of their draft. Reply helpfully and briefly to the conversation."
    )
    message = (
        (f'Passage in question: "{quote}".\n' if quote else "")
        + f"Comment: {(comment.body or '').strip()}\n"
        + (f"Thread so far:\n{thread}\n" if thread else "")
        + f"\nReply as {assistant}."
    )
    try:
        reply = await _core_chat(core, pid, system, message, selected_text=quote)
        return reply.strip() or f"({assistant} had nothing to add.)"
    except httpx.HTTPStatusError:
        return f"({assistant} is unavailable — configure an AI provider in LogosForge to enable @-mention replies.)"


async def maybe_ai_reply(core, pid: int, comment_id: str, text: str):
    """If `text` @-mentions Billy/Logos, append an AI reply to the thread and return
    the updated Comment; otherwise return None."""
    assistant = _detect_mention(text)
    if not assistant:
        return None
    from app.local_state import CommentReplyCreate, comments_store
    comment = next((c for c in comments_store.get(str(pid)).comments if c.id == comment_id), None)
    if comment is None:
        return None
    reply_text = await ai_reply_to_comment(core, pid, assistant, comment)
    return comments_store.add_reply(
        str(pid), comment_id, uuid.uuid4().hex, CommentReplyCreate(body=reply_text, author=assistant))


# -- endpoints ---------------------------------------------------------------

@router.post("/api/littleboy/billy/chat", response_model=BillyChatResponse)
async def billy_chat(request: Request, body: BillyChatRequest, doc: int | None = Query(None)):
    core = request.app.state.core
    pid = await resolve_pid(core, doc)
    conversation_id = (body.conversation_id or "").strip() or uuid.uuid4().hex
    mode = (body.writing_mode or "novel").strip() or "novel"

    # The "Billy" persona name is a Whiteboard product label (Pro's assistant is
    # not Billy), so it stays here as a thin system addendum; the CORE owns the
    # actual grounding/context from the editor fields passed below.
    system = (
        f"You are Billy, a concise, friendly writing assistant for {mode} writing "
        "inside the LogosForge Whiteboard. Help with the user's draft; keep replies short."
    )
    comments_ctx = _comments_context(pid)
    if comments_ctx:
        system = f"{system}\n\n{comments_ctx}"
    history = [m for m in (body.history or []) if m.role in ("user", "assistant") and m.content]

    try:
        content = await _core_chat(
            core, pid, system, body.message, history,
            selected_text=(body.selected_text or ""),
            nearby_text=(body.nearby_context or ""),
            document_title=(body.document_title or ""),
        )
        return BillyChatResponse(
            ok=True, conversation_id=conversation_id,
            message=ChatMessage(role="assistant", content=content),
            provider=await _provider_name(core, pid))
    except httpx.HTTPStatusError:
        if body.selected_text and body.selected_text.strip():
            extra = f" I can see your {len(body.selected_text.strip())}-character selection in {mode} mode."
        else:
            extra = f" I'd help with your {mode} writing here."
        return BillyChatResponse(
            ok=True, conversation_id=conversation_id,
            message=ChatMessage(
                role="assistant",
                content="Billy placeholder response. AI provider not configured yet." + extra),
            provider="stub", note=_NO_PROVIDER_NOTE)


@router.post("/api/littleboy/logos/inline", response_model=LogosResponse)
async def logos_inline(request: Request, body: LogosRequest, doc: int | None = Query(None)):
    """Run an inline Logos action through the CORE Logos engine (/logos/run).

    The wrapper only translates: it maps the frontend action name to the core
    registry name, pins the project, and reshapes the core LogosResult into the
    frontend LogosResponse — deriving suggested_replacement from the core's own
    ``generative`` flag (never a wrapper-local action list). A core action error
    (no/failed provider) degrades to the stable placeholder shape the frontend
    expects."""
    core = request.app.state.core
    pid = await resolve_pid(core, doc)
    front_action = (body.action or "rewrite").strip().lower()
    core_action = _CORE_ACTION.get(front_action, "inline_suggest")
    selected = (body.selected_text or "").strip()

    comments_ctx = _comments_context(pid)
    nearby = (body.nearby_context or "").strip()
    if comments_ctx:
        nearby = f"{nearby}\n\n{comments_ctx}".strip()
    run_body = {
        "action": core_action,
        "section": "Inline",
        "selected_text": selected,
        "nearby_context": nearby,
        "writing_mode": (body.writing_mode or "").strip(),
    }
    try:
        data = (await core.request(
            "POST", f"/api/projects/{pid}/logos/run", json=run_body)).json()
    except Exception:  # transport/project error -> degrade below
        data = {"ok": False}

    if data.get("ok"):
        message = data.get("message", "")
        # Apply-able replacement only for generative transforms over a selection —
        # read straight from the core's generative flag.
        replacement = message if (data.get("generative") and selected) else None
        provider = ("psyke" if core_action == "connect_to_psyke"
                    else await _provider_name(core, pid))
        return LogosResponse(
            ok=True, action=front_action, result=message,
            suggested_replacement=replacement, provider=provider)

    return LogosResponse(
        ok=True, action=front_action,
        result=f"Logos placeholder response for action: {front_action}. "
               "Connect an AI provider for a real result.",
        suggested_replacement=None, provider="stub", note=_NO_PROVIDER_NOTE)
