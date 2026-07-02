"""Voice Commit Router — safe, mode-aware transcript commit targets (Phase 2).

After local transcription the user **reviews** the transcript, **chooses** a
target and **explicitly commits** — this module decides which targets exist
for the current writing mode, validates them, and executes the commit. It is
pure logic (no Qt): the voice panel supplies a :class:`VoiceCommitContext`
built by the main window.

Hard rules (Alpha):

* listing/previewing targets never mutates anything — only
  :func:`commit_transcript` writes, and only after explicit user action;
* no automatic target guessing, no command execution, no LLM classification,
  no character-name guessing, no panel-field guessing, no image prompts;
* a transcript captured in one project can never be committed into another
  (the project id is checked at commit time);
* unsupported targets are listed **disabled with a reason** rather than
  hidden, so the UI can explain itself — and they stay inert.

Deferred by design (each listed disabled with its reason): Outline /
Series-episode draft items (the outline is scene-derived; there is no safe
"unclassified draft" area yet) and append-to-manuscript (the open editor owns
the scene body — a direct DB append could clobber unsaved editor state; the
cursor target covers that flow).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from logosforge.voice.types import TranscriptSegment

# Target ids (stable; the UI stores/restores selection by id).
T_CURSOR = "active_cursor"
T_NOTE = "note"
T_PSYKE = "psyche_draft_entry"
T_OUTLINE = "outline_draft_item"
T_MANUSCRIPT_APPEND = "manuscript_append"
T_SP_ACTION = "screenplay_action"
T_SP_DIALOGUE = "screenplay_dialogue"
T_GN_VISUAL = "graphic_panel_visual"
T_GN_CAPTION = "graphic_panel_caption"
T_GN_DIALOGUE = "graphic_panel_dialogue"
T_GN_SFX = "graphic_panel_sfx"
T_GN_NOTES = "graphic_panel_notes"
T_STAGE_DIRECTION = "stage_direction"
T_STAGE_DIALOGUE = "stage_dialogue"
T_SERIES_EPISODE_OUTLINE = "series_episode_outline_item"

_GN_FIELD_BY_TARGET = {
    T_GN_VISUAL: "visual_description",
    T_GN_CAPTION: "caption",
    T_GN_DIALOGUE: "dialogue",
    T_GN_SFX: "sfx",
    T_GN_NOTES: "notes",
}

PSYKE_ENTRY_TYPES = ("other", "character", "place", "object", "lore", "theme")

_REASON_NO_EDITOR = "Click into an editor first."
_REASON_NO_PANEL = "Select a Panel first."
_REASON_NO_CHARACTER = "Pick a character first."
_REASON_OUTLINE = "Outline voice target not available yet."
_REASON_APPEND = ("Use cursor insert — the open editor owns the scene body.")
_REASON_PROJECT_CHANGED = ("Project changed since transcription. Review "
                           "before committing.")


@dataclass
class CommitTarget:
    """One selectable commit destination (may be disabled with a reason)."""

    id: str
    label: str
    mode: str
    enabled: bool
    target_type: str
    reason_if_disabled: str = ""
    target_ref: tuple | None = None


@dataclass
class VoiceCommitContext:
    """Everything the router may inspect. Building one mutates nothing."""

    db: object
    project_id: int
    writing_mode: str = "novel"
    # Cursor insertion (the existing EditorCommitTarget path).
    has_active_editor: bool = False
    insert_at_cursor: Callable[[str], bool] | None = None
    # Optional: returns the live editor widget (for undo support only).
    active_editor_getter: Callable[[], object] | None = None
    # Graphic Novel: the panel whose script block was last focused —
    # (scene_id, page_idx, panel_idx) — or None.
    gn_panel_ref: tuple[int, int, int] | None = None
    # Explicit user selections from the panel UI (never guessed).
    psyke_entry_type: str = "other"
    character_name: str = ""
    # Phase 4 (Intent mode): explicit GN field choice + optional AI text
    # transform via the app's EXISTING provider (text-only; never audio).
    gn_field_choice: str = "visual_description"
    ai_complete: Callable[[str], str] | None = None
    # Project the transcript was captured in (None = not captured yet).
    transcript_project_id: int | None = None
    extras: dict = field(default_factory=dict)


# ---------------------------------------------------------------- helpers
def _gn_panel_exists(ctx: VoiceCommitContext) -> bool:
    if ctx.gn_panel_ref is None:
        return False
    scene_id, page_idx, panel_idx = ctx.gn_panel_ref
    try:
        scene = ctx.db.get_scene_by_id(scene_id)
        if scene is None or scene.project_id != ctx.project_id:
            return False
        from logosforge import graphic_novel_blocks as gnb
        script = gnb.load_scene_script(ctx.db, scene_id)
        return (0 <= page_idx < len(script.pages)
                and 0 <= panel_idx < len(script.pages[page_idx].panels))
    except Exception:
        return False


def _cursor_target(ctx: VoiceCommitContext, target_id: str, label: str,
                   *, enabled: bool = True, reason: str = "") -> CommitTarget:
    ok = bool(ctx.has_active_editor and ctx.insert_at_cursor is not None)
    if not ok:
        enabled, reason = False, _REASON_NO_EDITOR
    return CommitTarget(id=target_id, label=label, mode=ctx.writing_mode,
                        enabled=enabled, target_type=target_id,
                        reason_if_disabled=reason if not enabled else "")


def _note_title(text: str) -> str:
    head = " ".join((text or "").split())[:40].strip()
    return f"Voice note — {head}" if head else "Voice note"


# ------------------------------------------------------------------- API
def get_available_voice_commit_targets(
        ctx: VoiceCommitContext) -> list[CommitTarget]:
    """List targets for the context's mode. Read-only — never mutates."""
    mode = (ctx.writing_mode or "novel").lower()
    targets: list[CommitTarget] = [
        _cursor_target(ctx, T_CURSOR, "Insert at cursor"),
        CommitTarget(id=T_NOTE, label="New Note (Voice note)", mode=mode,
                     enabled=True, target_type=T_NOTE),
        CommitTarget(id=T_PSYKE, label="PSYKE draft entry", mode=mode,
                     enabled=True, target_type=T_PSYKE),
        CommitTarget(id=T_MANUSCRIPT_APPEND, label="Append to Manuscript",
                     mode=mode, enabled=False, target_type=T_MANUSCRIPT_APPEND,
                     reason_if_disabled=_REASON_APPEND),
        CommitTarget(id=T_OUTLINE, label="Outline draft item", mode=mode,
                     enabled=False, target_type=T_OUTLINE,
                     reason_if_disabled=_REASON_OUTLINE),
    ]

    if mode == "screenplay":
        targets.append(_cursor_target(ctx, T_SP_ACTION, "Insert as Action"))
        dlg = _cursor_target(ctx, T_SP_DIALOGUE,
                             "Insert as Dialogue (chosen character)")
        if dlg.enabled and not (ctx.character_name or "").strip():
            dlg.enabled = False
            dlg.reason_if_disabled = _REASON_NO_CHARACTER
        targets.append(dlg)
    elif mode == "graphic_novel":
        panel_ok = _gn_panel_exists(ctx)
        for tid, label in ((T_GN_VISUAL, "Panel → Visual"),
                           (T_GN_CAPTION, "Panel → Caption"),
                           (T_GN_DIALOGUE, "Panel → Dialogue"),
                           (T_GN_SFX, "Panel → SFX"),
                           (T_GN_NOTES, "Panel → Notes")):
            targets.append(CommitTarget(
                id=tid, label=label, mode=mode, enabled=panel_ok,
                target_type=tid,
                reason_if_disabled="" if panel_ok else _REASON_NO_PANEL,
                target_ref=ctx.gn_panel_ref if panel_ok else None))
    elif mode == "stage_script":
        targets.append(_cursor_target(ctx, T_STAGE_DIRECTION,
                                      "Insert as Stage Direction"))
        dlg = _cursor_target(ctx, T_STAGE_DIALOGUE,
                             "Insert as Dialogue (chosen character)")
        if dlg.enabled and not (ctx.character_name or "").strip():
            dlg.enabled = False
            dlg.reason_if_disabled = _REASON_NO_CHARACTER
        targets.append(dlg)
    elif mode == "series":
        targets.append(CommitTarget(
            id=T_SERIES_EPISODE_OUTLINE, label="Episode Outline draft item",
            mode=mode, enabled=False, target_type=T_SERIES_EPISODE_OUTLINE,
            reason_if_disabled=_REASON_OUTLINE))
    return targets


def validate_voice_commit_target(target_id: str,
                                 ctx: VoiceCommitContext) -> tuple[bool, str]:
    """Re-check one target against the LIVE context (read-only)."""
    if (ctx.transcript_project_id is not None
            and ctx.transcript_project_id != ctx.project_id):
        return False, _REASON_PROJECT_CHANGED
    for target in get_available_voice_commit_targets(ctx):
        if target.id == target_id:
            if target.enabled:
                return True, ""
            return False, target.reason_if_disabled or "Target unavailable."
    return False, "Target unavailable."


def preview_commit_target(target_id: str, ctx: VoiceCommitContext) -> str:
    """Human description of what commit WOULD do. Never mutates."""
    for target in get_available_voice_commit_targets(ctx):
        if target.id == target_id:
            if not target.enabled:
                return target.reason_if_disabled or "Target unavailable."
            return f"Commit inserts the transcript into: {target.label}"
    return "Target unavailable."


def commit_transcript(segment: TranscriptSegment | str, target_id: str,
                      ctx: VoiceCommitContext) -> tuple[bool, str]:
    """Execute ONE explicit commit. Returns (ok, status message)."""
    ok, message, _op = commit_transcript_op(segment, target_id, ctx)
    return ok, message


def commit_transcript_op(
        segment: TranscriptSegment | str, target_id: str,
        ctx: VoiceCommitContext) -> tuple[bool, str, "CommitOperation | None"]:
    """Like :func:`commit_transcript`, but also returns the undo record."""
    seg = (segment if isinstance(segment, TranscriptSegment)
           else TranscriptSegment(text=str(segment)))
    text = (seg.text or "").strip()
    if not text:
        return False, "Nothing to commit.", None
    ok, reason = validate_voice_commit_target(target_id, ctx)
    if not ok:
        return False, reason, None

    target = next(t for t in get_available_voice_commit_targets(ctx)
                  if t.id == target_id)
    done, message, op = _execute(text, target, ctx)
    if done:
        seg.committed = True
        seg.committed_target = target_id
        seg.committed_at = time.time()
        message = message or f"Transcript committed to {target.label}."
    return done, message, op


@dataclass
class CommitOperation:
    """Undo record for ONE voice commit (single-level; target-scoped)."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    target_id: str = ""
    label: str = ""
    project_id: int = 0
    kind: str = ""                       # cursor | gn_field | note | psyke
    # cursor-family
    editor: object = None
    doc_revision: int | None = None
    inserted_text: str = ""
    # gn_field
    gn_ref: tuple | None = None
    gn_field: str = ""
    gn_prev_value: str = ""
    gn_new_value: str = ""
    # note / psyke
    created_id: int | None = None
    created_text: str = ""


UNDO_UNAVAILABLE = "Undo is not available for this target."
UNDO_CHANGED = "Undo blocked: the target changed since the commit."
UNDO_PROJECT = "Undo blocked: project changed since the commit."


def _cursor_insert_op(ctx: VoiceCommitContext, target: CommitTarget,
                      rendered: str) -> tuple[bool, str, CommitOperation | None]:
    """Insert *rendered* at the cursor and build the cursor undo record."""
    editor = None
    if ctx.active_editor_getter is not None:
        try:
            editor = ctx.active_editor_getter()
        except Exception:
            editor = None
    ok = bool(ctx.insert_at_cursor and ctx.insert_at_cursor(rendered))
    if not ok:
        return False, "No active editor — click into the editor, then Commit.", None
    op = CommitOperation(target_id=target.id, label=target.label,
                         project_id=ctx.project_id, kind="cursor",
                         editor=editor, inserted_text=rendered)
    try:                                  # one insertText call == one undo step
        op.doc_revision = editor.document().revision()
    except Exception:
        op.doc_revision = None            # QLineEdit / gone -> undo unsupported
    return True, "", op


def _execute(text: str, target: CommitTarget, ctx: VoiceCommitContext
             ) -> tuple[bool, str, CommitOperation | None]:
    tid = target.id

    if tid == T_CURSOR:
        return _cursor_insert_op(ctx, target, text)
    if tid == T_SP_ACTION:
        return _cursor_insert_op(ctx, target, f"\n\n{text}\n\n")
    if tid == T_SP_DIALOGUE:
        name = (ctx.character_name or "").strip().upper()
        return _cursor_insert_op(ctx, target, f"\n\n{name}\n{text}\n\n")
    if tid == T_STAGE_DIRECTION:
        return _cursor_insert_op(ctx, target, f"\n\nSTAGE: {text}\n\n")
    if tid == T_STAGE_DIALOGUE:
        name = (ctx.character_name or "").strip().upper()
        return _cursor_insert_op(ctx, target,
                                 f"\n\nCHARACTER: {name}\n{text}\n\n")

    if tid == T_NOTE:
        note = ctx.db.create_note(ctx.project_id, _note_title(text),
                                  content=text)
        op = CommitOperation(target_id=tid, label=target.label,
                             project_id=ctx.project_id, kind="note",
                             created_id=note.id, created_text=text)
        return True, "", op

    if tid == T_PSYKE:
        entry_type = (ctx.psyke_entry_type or "other").lower()
        if entry_type not in PSYKE_ENTRY_TYPES:
            entry_type = "other"        # never guessed, never widened
        entry = ctx.db.create_psyke_entry(ctx.project_id, _note_title(text),
                                          entry_type=entry_type, notes=text)
        op = CommitOperation(target_id=tid, label=target.label,
                             project_id=ctx.project_id, kind="psyke",
                             created_id=entry.id, created_text=text)
        return True, "", op

    if tid in _GN_FIELD_BY_TARGET:
        if target.target_ref is None:
            return False, _REASON_NO_PANEL, None
        scene_id, page_idx, panel_idx = target.target_ref
        field_name = _GN_FIELD_BY_TARGET[tid]
        from logosforge import graphic_novel_blocks as gnb
        from logosforge import graphic_novel_outline as gno
        script = gnb.load_scene_script(ctx.db, scene_id)
        try:
            existing = getattr(script.pages[page_idx].panels[panel_idx],
                               field_name, "")
        except IndexError:
            return False, _REASON_NO_PANEL, None
        value = f"{existing}\n{text}" if (existing or "").strip() else text
        done = gno.set_panel_field(ctx.db, scene_id, page_idx, panel_idx,
                                   field_name, value)
        if not done:
            return False, _REASON_NO_PANEL, None
        op = CommitOperation(target_id=tid, label=target.label,
                             project_id=ctx.project_id, kind="gn_field",
                             gn_ref=(scene_id, page_idx, panel_idx),
                             gn_field=field_name, gn_prev_value=existing,
                             gn_new_value=value)
        return True, "", op

    return False, "Target unavailable.", None


# ----------------------------------------------------------------- undo
def can_undo(op: CommitOperation | None,
             ctx: VoiceCommitContext) -> tuple[bool, str]:
    """Whether the LAST voice commit can be undone safely (read-only)."""
    if op is None:
        return False, "Nothing to undo."
    if op.project_id != ctx.project_id:
        return False, UNDO_PROJECT
    if op.kind == "cursor":
        if op.editor is None or op.doc_revision is None:
            return False, UNDO_UNAVAILABLE
        try:
            current = op.editor.document().revision()
        except Exception:
            return False, UNDO_UNAVAILABLE
        if current != op.doc_revision:
            return False, UNDO_CHANGED    # never undo unrelated user edits
        return True, ""
    if op.kind == "gn_field":
        try:
            from logosforge import graphic_novel_blocks as gnb
            scene_id, page_idx, panel_idx = op.gn_ref
            script = gnb.load_scene_script(ctx.db, scene_id)
            current = getattr(script.pages[page_idx].panels[panel_idx],
                              op.gn_field, None)
        except Exception:
            return False, UNDO_CHANGED
        return ((True, "") if current == op.gn_new_value
                else (False, UNDO_CHANGED))
    if op.kind == "note":
        note = ctx.db.get_note_by_id(op.created_id)
        if note is None or note.content != op.created_text:
            return False, UNDO_CHANGED
        return True, ""
    if op.kind == "psyke":
        entry = ctx.db.get_psyke_entry_by_id(op.created_id)
        if entry is None or entry.notes != op.created_text:
            return False, UNDO_CHANGED
        return True, ""
    return False, UNDO_UNAVAILABLE


def undo_commit(op: CommitOperation | None,
                ctx: VoiceCommitContext) -> tuple[bool, str]:
    """Undo the LAST voice commit (validated; never touches anything else)."""
    ok, reason = can_undo(op, ctx)
    if not ok:
        return False, reason
    if op.kind == "cursor":
        try:
            op.editor.undo()              # exactly our single insert step
        except Exception:
            return False, UNDO_UNAVAILABLE
        return True, "Voice commit undone."
    if op.kind == "gn_field":
        from logosforge import graphic_novel_outline as gno
        scene_id, page_idx, panel_idx = op.gn_ref
        done = gno.set_panel_field(ctx.db, scene_id, page_idx, panel_idx,
                                   op.gn_field, op.gn_prev_value)
        return ((True, "Voice commit undone.") if done
                else (False, UNDO_CHANGED))
    if op.kind == "note":
        ctx.db.delete_note(op.created_id)
        return True, "Voice commit undone."
    if op.kind == "psyke":
        ctx.db.delete_psyke_entry(op.created_id)
        return True, "Voice commit undone."
    return False, UNDO_UNAVAILABLE
