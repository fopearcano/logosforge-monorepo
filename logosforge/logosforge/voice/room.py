"""Dexter's Room shell core (Phase 6): state, context, queue.

Internal note: these ``VoiceRoom*`` names power the user-facing
**Dexter's Room** workspace (the names are deliberately retained — renaming
internals would be churn without benefit). "Live Writer Room" remains the
name of the DEFERRED future autonomy concept only.

The room is the unifying layer over the local voice stack: one
session workflow connecting listening → buffered transcription → transcript
history → (Dictation | Intent | Ask Billy | Edit with Billy) → preview →
explicit apply/cancel/undo. It is **local and review-first**: not cloud
realtime, not voice-to-voice, not an autonomous agent — nothing mutates
without confirmation, raw audio never reaches Billy/AI, and the user picks
the workflow mode explicitly (never inferred from the transcript).

Pure logic (no Qt): the voice panel renders it. Three pieces live here —

* :class:`VoiceRoomStateMachine` — explicit session states with an allowed-
  transition table; invalid transitions return ``False`` and never crash;
* :func:`build_voice_room_context` — the safe, refreshed-per-action session
  context (no API keys, no provider settings, no raw audio, no other
  projects);
* :class:`ProposalQueue` — the session-scoped queue of Intent previews and
  Billy proposals with draft/ready/applied/cancelled/stale/failed states;
  stale items (project switch / target drift) can never be applied.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from logosforge.voice import billy_bridge as bb
from logosforge.voice import intent_router as ir
from logosforge.voice.commit_router import VoiceCommitContext

# --------------------------------------------------------------------------
# Session state machine (§3)
# --------------------------------------------------------------------------

S_IDLE = "idle"
S_CHECKING_BACKEND = "checking_backend"
S_READY = "ready"
S_LISTENING = "listening"
S_SEGMENT_BUFFERING = "segment_buffering"
S_TRANSCRIBING = "transcribing"
S_TRANSCRIPT_READY = "transcript_ready"
S_CHOOSING_TARGET = "choosing_target"
S_SENDING_TO_BILLY = "sending_to_billy"
S_PROPOSAL_READY = "proposal_ready"
S_APPLYING = "applying"
S_APPLIED = "applied"
S_ERROR = "error"
S_STOPPED = "stopped"

# Any state may stop (safe app close) or error (non-crashing failures).
_ALWAYS_ALLOWED = {S_STOPPED, S_ERROR}

_TRANSITIONS: dict[str, set[str]] = {
    S_IDLE: {S_CHECKING_BACKEND, S_READY},
    S_CHECKING_BACKEND: {S_READY, S_IDLE},
    S_READY: {S_LISTENING, S_IDLE, S_CHOOSING_TARGET, S_SENDING_TO_BILLY},
    S_LISTENING: {S_SEGMENT_BUFFERING, S_TRANSCRIBING, S_TRANSCRIPT_READY,
                  S_READY},
    S_SEGMENT_BUFFERING: {S_TRANSCRIBING, S_LISTENING},
    S_TRANSCRIBING: {S_TRANSCRIPT_READY, S_LISTENING},
    S_TRANSCRIPT_READY: {S_CHOOSING_TARGET, S_SENDING_TO_BILLY, S_LISTENING,
                         S_READY, S_APPLYING},
    S_CHOOSING_TARGET: {S_APPLYING, S_SENDING_TO_BILLY, S_TRANSCRIPT_READY,
                        S_READY},
    S_SENDING_TO_BILLY: {S_PROPOSAL_READY, S_TRANSCRIPT_READY, S_READY},
    S_PROPOSAL_READY: {S_APPLYING, S_SENDING_TO_BILLY, S_TRANSCRIPT_READY,
                       S_READY},
    S_APPLYING: {S_APPLIED, S_PROPOSAL_READY, S_READY},
    S_APPLIED: {S_READY, S_LISTENING, S_TRANSCRIPT_READY,
                S_CHOOSING_TARGET},
    S_ERROR: {S_READY, S_IDLE},
    S_STOPPED: {S_IDLE, S_READY},
}


class VoiceRoomStateMachine:
    """Explicit, crash-proof session states. UI reads ``state``."""

    def __init__(self) -> None:
        self.state = S_IDLE
        self.history: list[str] = [S_IDLE]

    def can(self, new_state: str) -> bool:
        if new_state in _ALWAYS_ALLOWED:
            return True
        return new_state in _TRANSITIONS.get(self.state, set())

    def to(self, new_state: str) -> bool:
        """Transition if allowed; otherwise stay put and return False."""
        if new_state == self.state:
            return True
        if not self.can(new_state):
            return False
        self.state = new_state
        self.history.append(new_state)
        return True


# --------------------------------------------------------------------------
# Dexter's Room context (§4) — safe, refreshed, validated
# --------------------------------------------------------------------------


@dataclass
class VoiceRoomContext:
    session_id: str = ""
    project_id: int = 0
    project_title: str = ""
    writing_mode: str = ""
    active_section: str = ""
    current_scene_id: int | None = None
    current_graphic_page_index: int | None = None
    current_graphic_panel_index: int | None = None
    selected_panel_field: str = ""
    selected_text_snapshot: str = ""
    has_active_editor: bool = False
    billy_available: bool = False
    transcript_segment_ids: list[str] = field(default_factory=list)
    pending_proposal_ids: list[str] = field(default_factory=list)
    last_operation_id: str = ""
    created_at: float = field(default_factory=time.time)


def build_voice_room_context(ctx: VoiceCommitContext, history=None,
                             queue: "ProposalQueue | None" = None,
                             *, active_section: str = ""
                             ) -> VoiceRoomContext:
    """Package the CURRENT session context. Read-only; text only — never
    API keys, provider settings, raw audio, or other projects' data."""
    _editor, selection = ir._editor_selection(ctx)
    room = VoiceRoomContext(
        session_id=(history.session.id
                    if history is not None and history.session else ""),
        project_id=ctx.project_id,
        project_title=str((ctx.extras or {}).get("project_title", "")),
        writing_mode=ctx.writing_mode or "",
        active_section=active_section
        or str((ctx.extras or {}).get("active_section", "")),
        selected_text_snapshot=selection[:2000],
        has_active_editor=bool(ctx.has_active_editor),
        billy_available=getattr(ctx, "ai_complete", None) is not None,
    )
    if ctx.gn_panel_ref is not None:
        scene_id, page_idx, panel_idx = ctx.gn_panel_ref
        room.current_scene_id = scene_id
        room.current_graphic_page_index = page_idx
        room.current_graphic_panel_index = panel_idx
        room.selected_panel_field = getattr(ctx, "gn_field_choice", "")
    if history is not None:
        room.transcript_segment_ids = [e.id for e in history.entries]
        if history.last_commit_op is not None:
            room.last_operation_id = history.last_commit_op.id
    if queue is not None:
        room.pending_proposal_ids = [q.id for q in queue.pending()]
    return room


def context_summary_line(room: VoiceRoomContext) -> str:
    bits = [room.project_title or f"project {room.project_id}",
            room.writing_mode or "novel"]
    if room.active_section:
        bits.append(room.active_section)
    if room.current_graphic_panel_index is not None:
        bits.append(f"Panel {room.current_graphic_panel_index + 1} on Page "
                    f"{(room.current_graphic_page_index or 0) + 1}")
        if room.selected_panel_field:
            bits.append(room.selected_panel_field)
    bits.append("text selected" if room.selected_text_snapshot
                else "no selection")
    return " · ".join(bits)


# --------------------------------------------------------------------------
# Proposal queue (§5) — session-scoped, preview-first
# --------------------------------------------------------------------------

Q_DRAFT = "draft"
Q_READY = "ready"
Q_APPLIED = "applied"
Q_CANCELLED = "cancelled"
Q_STALE = "stale"
Q_FAILED = "failed"


@dataclass
class QueuedProposal:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    kind: str = ""                       # "billy" | "intent"
    label: str = ""
    project_id: int = 0
    status: str = Q_DRAFT
    payload: object = None               # BillyVoiceProposal | IntentPreview
    operation_id: str = ""
    reason: str = ""
    created_at: float = field(default_factory=time.time)


class ProposalQueue:
    """Pending/applied/cancelled proposals for THIS session. Local only."""

    def __init__(self) -> None:
        self.items: list[QueuedProposal] = []

    # ---------------------------------------------------------------- intake
    def add_billy(self, proposal) -> QueuedProposal:
        item = QueuedProposal(
            kind="billy", payload=proposal,
            label=proposal.target_summary or proposal.operation,
            project_id=proposal.project_id,
            status=Q_READY if proposal.can_apply else Q_DRAFT,
            reason=proposal.reason_if_blocked)
        self.items.append(item)
        return item

    def add_intent(self, preview) -> QueuedProposal:
        item = QueuedProposal(
            kind="intent", payload=preview,
            label=preview.target_summary or preview.intent_type,
            project_id=preview.project_id,
            status=Q_READY if preview.can_apply else Q_DRAFT,
            reason=preview.reason_if_blocked)
        self.items.append(item)
        return item

    def get(self, item_id: str) -> QueuedProposal | None:
        return next((i for i in self.items if i.id == item_id), None)

    def pending(self) -> list[QueuedProposal]:
        return [i for i in self.items if i.status in (Q_DRAFT, Q_READY)]

    # --------------------------------------------------------------- staleness
    def mark_stale(self, item_id: str, reason: str) -> None:
        item = self.get(item_id)
        if item is not None and item.status in (Q_DRAFT, Q_READY):
            item.status = Q_STALE
            item.reason = reason

    def mark_all_stale(self, reason: str) -> int:
        count = 0
        for item in self.items:
            if item.status in (Q_DRAFT, Q_READY):
                item.status = Q_STALE
                item.reason = reason
                count += 1
        return count

    def on_project_switch(self, new_project_id: int) -> int:
        """Project-bound proposals from another project become stale."""
        count = 0
        for item in self.items:
            if item.status in (Q_DRAFT, Q_READY) \
                    and item.project_id != new_project_id:
                item.status = Q_STALE
                item.reason = bb.BILLY_PROJECT_CHANGED
                count += 1
        return count

    # ------------------------------------------------------------ apply/cancel
    def apply(self, item_id: str, ctx: VoiceCommitContext
              ) -> tuple[bool, str, object]:
        """Apply ONE queued proposal (explicit). Stale/finished items refuse;
        a live-validation failure marks the item stale instead of crashing."""
        item = self.get(item_id)
        if item is None:
            return False, "Proposal not found.", None
        if item.status == Q_STALE:
            return False, item.reason or bb.BILLY_TARGET_CHANGED, None
        if item.status not in (Q_READY,):
            return False, "Nothing to apply.", None
        if item.kind == "billy":
            ok, msg, op = bb.apply_billy_voice_proposal(item.payload, ctx)
        else:
            ok, msg, op = ir.apply_intent_preview(item.payload, ctx)
        if ok:
            item.status = Q_APPLIED
            item.operation_id = getattr(op, "id", "") if op else ""
        else:
            stale = (msg in (bb.BILLY_TARGET_CHANGED, bb.BILLY_PROJECT_CHANGED,
                             ir.STALE_PREVIEW))
            item.status = Q_STALE if stale else Q_FAILED
            item.reason = msg
        return ok, msg, op

    def cancel(self, item_id: str) -> bool:
        item = self.get(item_id)
        if item is None or item.status in (Q_APPLIED, Q_CANCELLED):
            return False
        if item.kind == "billy":
            bb.cancel_billy_voice_proposal(item.payload)
        item.status = Q_CANCELLED
        return True
