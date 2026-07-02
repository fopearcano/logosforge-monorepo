"""Billy Voice Bridge — voice transcript → Billy proposal → confirmed apply.

"Billy" is the app's hovering AI chat agent (the Assistant). This bridge
lets the user send **selected transcript text** to Billy as a question or an
editing instruction and get back a *proposal* — never a mutation. Billy
receives **text only** (transcript + a minimal, safe writing context);
audio, API keys, provider settings and unrelated project data are never
packaged. All AI calls go through the app's existing Assistant/provider
infrastructure (the injected ``ctx.ai_complete`` — `build_active_provider`
+ the shared chat completion); no new provider system, nothing chosen
silently, and with no provider configured every Billy action is disabled
with: *"Billy is not configured. Voice-to-Billy actions are unavailable."*

Every proposal is preview-first: Apply is explicit, Cancel discards with
zero mutation, and apply routes through the existing safe layers (the
Phase 4 Intent Router / Phase 2 Commit Router), inheriting their live
re-validation and the Phase 3 undo records. This is NOT voice-command
execution: dangerous instructions ("delete the project", "run this
command", "send to ComfyUI", …) are never executed — they come back as a
chat-only response: *"I can't perform that action from voice in Alpha."*
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field

from logosforge.voice import intent_router as ir
from logosforge.voice.commit_router import (
    CommitOperation,
    T_CURSOR,
    VoiceCommitContext,
    commit_transcript_op,
)

# Operation ids (fixed allowlist).
OP_ASK = "billy_ask"
OP_REWRITE_SELECTION = "billy_rewrite_selection"
OP_CONTINUE_CURSOR = "billy_continue_cursor"
OP_SUMMARIZE_NOTE = "billy_summarize_note"
OP_OUTLINE_ITEM = "billy_outline_item"
OP_PSYKE_DRAFT = "billy_psyke_draft"
OP_GN_PANEL_FIELD = "billy_gn_panel_field"

# Proposal types (§5).
P_CHAT_ONLY = "chat_only"
P_REPLACE_SELECTION = "replace_selection"
P_INSERT_AT_CURSOR = "insert_at_cursor"
P_NOTE_DRAFT = "note_draft"
P_PSYKE_DRAFT = "psyke_draft"
P_GN_PANEL_FIELD = "graphic_panel_field"

BILLY_UNCONFIGURED = ("Billy is not configured. Voice-to-Billy actions are "
                      "unavailable.")
BILLY_TARGET_CHANGED = ("Target changed since Billy generated this proposal. "
                        "Regenerate before applying.")
BILLY_PROJECT_CHANGED = ("Project changed since this proposal was generated. "
                         "Switch back or regenerate.")
BILLY_CANT_DO_THAT = "I can't perform that action from voice in Alpha."
NO_TRANSCRIPT = "Select a transcript segment first."

# Spoken instructions that must NEVER execute anything (§11). Matched as
# substrings of the lowered transcript; the response is chat-only.
_DANGEROUS = (
    "delete the project", "delete this project", "delete the scene",
    "delete all", "move all scenes", "comfyui", "image generation",
    "generate an image", "run this command", "run command", "open terminal",
    "open a terminal", "upload this", "upload the", "rm -rf", "format the",
    "execute ", "shell command", "system command",
)


@dataclass
class BillyVoiceProposal:
    """One Billy proposal (preview only until explicitly applied)."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    proposal_type: str = P_CHAT_ONLY
    operation: str = OP_ASK
    project_id: int = 0
    created_at: float = field(default_factory=time.time)
    source_segment_ids: list[str] = field(default_factory=list)
    prompt_text: str = ""                # what Billy was asked (text only)
    response_text: str = ""              # Billy's raw answer
    target_summary: str = ""
    before_text: str | None = None
    after_text: str | None = None
    diff: str | None = None
    note_preview: dict | None = None
    psyke_preview: dict | None = None
    gn_ref: tuple | None = None
    gn_field: str = ""
    can_apply: bool = False
    reason_if_blocked: str = ""
    applied: bool = False
    cancelled: bool = False
    applied_at: float | None = None


def _has_billy(ctx: VoiceCommitContext) -> bool:
    return getattr(ctx, "ai_complete", None) is not None


def _dangerous(text: str) -> bool:
    low = " ".join((text or "").lower().split())
    return any(marker in low for marker in _DANGEROUS)


def get_available_billy_operations(ctx: VoiceCommitContext) -> list:
    """(id, label, enabled, reason) per operation. Read-only."""
    has_billy = _has_billy(ctx)
    _editor, selection = ir._editor_selection(ctx)
    cursor_ok = bool(ctx.has_active_editor and ctx.insert_at_cursor)
    mode = (ctx.writing_mode or "novel").lower()

    def op(op_id, label, enabled=True, reason=""):
        if not has_billy:
            return (op_id, label, False, BILLY_UNCONFIGURED)
        return (op_id, label, enabled, "" if enabled else reason)

    ops = [
        op(OP_ASK, "Ask Billy"),
        op(OP_REWRITE_SELECTION, "Rewrite selected text",
           enabled=bool(selection), reason=ir.NO_SELECTION),
        op(OP_CONTINUE_CURSOR, "Continue from cursor",
           enabled=cursor_ok, reason="Click into an editor first."),
        op(OP_SUMMARIZE_NOTE, "Summarize to Note"),
        op(OP_OUTLINE_ITEM, "Propose Outline item", enabled=False,
           reason="Outline voice target not available yet."),
        op(OP_PSYKE_DRAFT, "Propose PSYKE draft (chosen type)"),
    ]
    if mode == "graphic_novel":
        from logosforge.voice.commit_router import _gn_panel_exists
        panel_ok = _gn_panel_exists(ctx)
        ops.append(op(OP_GN_PANEL_FIELD,
                      "Propose Panel field update (chosen field)",
                      enabled=panel_ok, reason="Select a Panel first."))
    return ops


# ===========================================================================
# Context packaging (§4) — minimal, safe, text-only
# ===========================================================================

def build_billy_voice_context(transcript_text: str,
                              ctx: VoiceCommitContext) -> dict:
    """The safe context dict sent to Billy as part of the prompt. Never
    includes API keys, provider settings, audio, or unrelated projects."""
    _editor, selection = ir._editor_selection(ctx)
    packaged = {
        "project_id": ctx.project_id,
        "project_title": str((ctx.extras or {}).get("project_title", "")),
        "writing_mode": ctx.writing_mode,
        "scene_path": str((ctx.extras or {}).get("scene_path", "")),
        "selected_text": selection[:2000],
        "transcript": (transcript_text or "")[:4000],
    }
    if (ctx.writing_mode or "").lower() == "graphic_novel" \
            and ctx.gn_panel_ref is not None:
        try:
            from logosforge import graphic_novel_blocks as gnb
            scene_id, page_idx, panel_idx = ctx.gn_panel_ref
            panel = (gnb.load_scene_script(ctx.db, scene_id)
                     .pages[page_idx].panels[panel_idx])
            packaged["panel"] = {
                "page": page_idx + 1, "panel": panel_idx + 1,
                "visual": panel.visual_description, "caption": panel.caption,
                "dialogue": panel.dialogue, "sfx": panel.sfx,
                "notes": panel.notes,
            }
        except Exception:
            pass
    return packaged


def _context_block(packaged: dict) -> str:
    lines = [f"Writing mode: {packaged.get('writing_mode', '')}"]
    if packaged.get("project_title"):
        lines.append(f"Project: {packaged['project_title']}")
    if packaged.get("scene_path"):
        lines.append(f"Location: {packaged['scene_path']}")
    if packaged.get("selected_text"):
        lines.append("Selected text:\n" + packaged["selected_text"])
    panel = packaged.get("panel")
    if panel:
        lines.append(
            "Selected panel (Page {page}, Panel {panel}):\n"
            "Visual: {visual}\nCaption: {caption}\nDialogue: {dialogue}\n"
            "SFX: {sfx}\nNotes: {notes}".format(**panel))
    return "\n".join(lines)


# ===========================================================================
# Proposal generation (§5) — preview only, never mutates
# ===========================================================================

def request_billy_proposal(operation: str, transcript_text: str,
                           ctx: VoiceCommitContext, *,
                           source_segment_ids: list[str] | None = None
                           ) -> BillyVoiceProposal:
    proposal = BillyVoiceProposal(
        operation=operation, project_id=ctx.project_id,
        source_segment_ids=list(source_segment_ids or []))
    text = (transcript_text or "").strip()
    if not _has_billy(ctx):
        proposal.reason_if_blocked = BILLY_UNCONFIGURED
        return proposal
    if not text:
        proposal.reason_if_blocked = NO_TRANSCRIPT
        return proposal
    enabled = {o[0]: (o[2], o[3])
               for o in get_available_billy_operations(ctx)}
    ok, reason = enabled.get(operation, (False, "Operation unavailable."))
    if not ok:
        proposal.reason_if_blocked = reason or "Operation unavailable."
        return proposal
    # §11: never execute anything — dangerous instructions get a chat-only
    # refusal without even calling the provider.
    if _dangerous(text):
        proposal.proposal_type = P_CHAT_ONLY
        proposal.response_text = BILLY_CANT_DO_THAT
        proposal.target_summary = "Chat answer (no document change)"
        return proposal

    packaged = build_billy_voice_context(text, ctx)
    context_block = _context_block(packaged)
    proposal.prompt_text = text

    if operation == OP_ASK:
        answer = ir._ai(ctx, "You are Billy, the writing assistant.\n"
                             + context_block
                             + "\n\nThe writer says (by voice):\n" + text
                             + "\n\nAnswer helpfully and briefly.")
        proposal.proposal_type = P_CHAT_ONLY
        proposal.response_text = answer or "Billy returned no answer."
        proposal.target_summary = "Chat answer (no document change)"
        return proposal

    if operation == OP_REWRITE_SELECTION:
        _editor, selection = ir._editor_selection(ctx)
        after = ir._ai(ctx, "Rewrite the selected text according to this "
                            "spoken instruction. Return ONLY the rewritten "
                            "text.\n" + context_block
                            + "\n\nInstruction:\n" + text)
        if not after:
            proposal.reason_if_blocked = "Billy returned no text."
            return proposal
        proposal.proposal_type = P_REPLACE_SELECTION
        proposal.before_text, proposal.after_text = selection, after
        proposal.diff = ir._diff(selection, after)
        proposal.response_text = after
        proposal.target_summary = "Replace the selected text in the editor"
        proposal.can_apply = True
        return proposal

    if operation == OP_CONTINUE_CURSOR:
        cont = ir._ai(ctx, "Continue the writing from the cursor according "
                           "to this spoken instruction. Return ONLY the "
                           "continuation text.\n" + context_block
                           + "\n\nInstruction:\n" + text)
        if not cont:
            proposal.reason_if_blocked = "Billy returned no text."
            return proposal
        proposal.proposal_type = P_INSERT_AT_CURSOR
        proposal.after_text = cont
        proposal.response_text = cont
        proposal.target_summary = "Insert at the cursor"
        proposal.can_apply = True
        return proposal

    if operation == OP_SUMMARIZE_NOTE:
        _editor, selection = ir._editor_selection(ctx)
        source = selection or text
        summary = ir._ai(ctx, "Summarize the following for a working note. "
                              "Return ONLY the summary.\n" + context_block
                              + "\n\nMaterial:\n" + source)
        if not summary:
            proposal.reason_if_blocked = "Billy returned no text."
            return proposal
        proposal.proposal_type = P_NOTE_DRAFT
        proposal.note_preview = {"title": ir._title(summary),
                                 "content": summary}
        proposal.after_text = summary
        proposal.response_text = summary
        proposal.target_summary = "Create a new Note"
        proposal.can_apply = True
        return proposal

    if operation == OP_PSYKE_DRAFT:
        entry_type = (ctx.psyke_entry_type or "other").lower()
        from logosforge.voice.commit_router import PSYKE_ENTRY_TYPES
        if entry_type not in PSYKE_ENTRY_TYPES:
            entry_type = "other"          # user-chosen only, never guessed
        body = ir._ai(ctx, "Draft a concise story-bible entry body from this "
                           "spoken idea. Return ONLY the entry text.\n"
                           + context_block + "\n\nIdea:\n" + text)
        if not body:
            proposal.reason_if_blocked = "Billy returned no text."
            return proposal
        proposal.proposal_type = P_PSYKE_DRAFT
        proposal.psyke_preview = {"name": ir._title(body),
                                  "entry_type": entry_type, "notes": body}
        proposal.after_text = body
        proposal.response_text = body
        proposal.target_summary = f"Create a PSYKE draft entry ({entry_type})"
        proposal.can_apply = True
        return proposal

    if operation == OP_GN_PANEL_FIELD:
        field_name = getattr(ctx, "gn_field_choice", "") or "visual_description"
        if field_name not in dict(ir.GN_FIELD_CHOICES):
            field_name = "visual_description"
        scene_id, page_idx, panel_idx = ctx.gn_panel_ref
        from logosforge import graphic_novel_blocks as gnb
        script = gnb.load_scene_script(ctx.db, scene_id)
        try:
            current = getattr(script.pages[page_idx].panels[panel_idx],
                              field_name, "")
        except IndexError:
            proposal.reason_if_blocked = "Select a Panel first."
            return proposal
        label = dict(ir.GN_FIELD_CHOICES)[field_name]
        after = ir._ai(ctx, f"Propose an updated {label} for the selected "
                            "comics panel according to this spoken "
                            "instruction. Return ONLY the new field text — "
                            "no image prompts.\n" + context_block
                            + "\n\nInstruction:\n" + text)
        if not after:
            proposal.reason_if_blocked = "Billy returned no text."
            return proposal
        proposal.proposal_type = P_GN_PANEL_FIELD
        proposal.before_text, proposal.after_text = current, after
        proposal.diff = ir._diff(current, after)
        proposal.response_text = after
        proposal.gn_ref = (scene_id, page_idx, panel_idx)
        proposal.gn_field = field_name
        proposal.target_summary = (f"Panel {panel_idx + 1} on Page "
                                   f"{page_idx + 1} — {label}")
        proposal.can_apply = True
        return proposal

    proposal.reason_if_blocked = "Operation unavailable."
    return proposal


# ===========================================================================
# Validate / apply / cancel (§6) — routed through the existing safe layers
# ===========================================================================

def _to_intent_preview(proposal: BillyVoiceProposal) -> ir.IntentPreview:
    preview = ir.IntentPreview(project_id=proposal.project_id,
                               can_apply=True)
    if proposal.proposal_type == P_REPLACE_SELECTION:
        preview.intent_type = ir.I_REWRITE_SELECTION
        preview.before_text = proposal.before_text
        preview.after_text = proposal.after_text
    elif proposal.proposal_type == P_NOTE_DRAFT:
        preview.intent_type = ir.I_SUMMARIZE_TO_NOTE
        preview.created_note_preview = dict(proposal.note_preview or {})
    elif proposal.proposal_type == P_PSYKE_DRAFT:
        preview.intent_type = ir.I_PSYKE_DRAFT
        preview.created_psyke_entry_preview = dict(proposal.psyke_preview or {})
    elif proposal.proposal_type == P_GN_PANEL_FIELD:
        preview.intent_type = ir.I_GN_PANEL_FIELD
        preview.before_text = proposal.before_text
        preview.after_text = proposal.after_text
        preview.gn_ref = proposal.gn_ref
        preview.gn_field = proposal.gn_field
    return preview


def validate_billy_proposal(proposal: BillyVoiceProposal | None,
                            ctx: VoiceCommitContext) -> tuple[bool, str]:
    if proposal is None or not proposal.can_apply:
        return False, (proposal.reason_if_blocked if proposal
                       else "No proposal.") or "Nothing to apply."
    if proposal.cancelled or proposal.applied:
        return False, "Nothing to apply."
    if proposal.project_id != ctx.project_id:
        return False, BILLY_PROJECT_CHANGED
    if proposal.proposal_type == P_INSERT_AT_CURSOR:
        if not (ctx.has_active_editor and ctx.insert_at_cursor):
            return False, BILLY_TARGET_CHANGED
        return True, ""
    if proposal.proposal_type == P_CHAT_ONLY:
        return False, "Nothing to apply."
    ok, _reason = ir.validate_intent_preview(_to_intent_preview(proposal), ctx)
    return (True, "") if ok else (False, BILLY_TARGET_CHANGED)


def apply_billy_voice_proposal(
        proposal: BillyVoiceProposal, ctx: VoiceCommitContext
) -> tuple[bool, str, CommitOperation | None]:
    """Explicit apply only — routed through the existing safe layers."""
    ok, reason = validate_billy_proposal(proposal, ctx)
    if not ok:
        return False, reason, None
    if proposal.proposal_type == P_INSERT_AT_CURSOR:
        done, msg, op = commit_transcript_op(proposal.after_text or "",
                                             T_CURSOR, ctx)
    else:
        done, msg, op = ir.apply_intent_preview(_to_intent_preview(proposal),
                                                ctx)
    if done:
        proposal.applied = True
        proposal.applied_at = time.time()
        msg = msg or "Billy proposal applied."
    elif not msg:
        msg = BILLY_TARGET_CHANGED
    return done, msg, op


def cancel_billy_voice_proposal(proposal: BillyVoiceProposal | None) -> None:
    if proposal is not None:
        proposal.cancelled = True
