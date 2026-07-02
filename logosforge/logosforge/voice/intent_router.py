"""Voice Intent Router — preview-first, confirmed text operations (Phase 4).

Two explicit modes for a transcript: **Dictation** (content — the Phase 2
Commit Router inserts it) and **Intent** (instruction — THIS module turns it
into a proposed operation with a preview, applied only after the user
confirms). Nothing is ever inferred automatically: the user switches to
Intent mode, picks the intent, clicks Preview, reviews before/after, then
Apply (or Cancel).

Hard rules (Alpha):

* listing intents and building previews never mutate anything; only
  :func:`apply_intent_preview` writes, after re-validating the live target
  (project id, target existence, and the expected ``before_text``);
* no voice-command execution, no shell/system access, no open-ended agent:
  the intent set is a fixed allowlist of low-risk text operations;
* AI is used ONLY for explicitly AI-backed intents, ONLY via the app's
  existing provider infrastructure (text in → text out; audio is never sent
  anywhere), and ONLY when a provider is configured — otherwise those
  intents are disabled with a clear message and the rule-based cleanup path
  still works;
* every applied intent produces the same :class:`CommitOperation` records
  Phase 3 uses, so "Undo last commit" covers intents too (editor
  revision-guarded; GN previous value; created Note/PSYKE deletion).
"""

from __future__ import annotations

import difflib
import re
import time
import uuid
from dataclasses import dataclass, field

from logosforge.voice.commit_router import (
    CommitOperation,
    T_OUTLINE,
    VoiceCommitContext,
    _GN_FIELD_BY_TARGET,
    commit_transcript_op,
    get_available_voice_commit_targets,
)

# Intent ids (fixed allowlist — nothing else can run).
I_CLEANUP = "cleanup_transcript"
I_INSERT_CLEANED = "insert_cleaned"
I_REWRITE_SELECTION = "rewrite_selection"
I_SUMMARIZE_TO_NOTE = "summarize_to_note"
I_OUTLINE_DRAFT = "send_to_outline_draft"
I_PSYKE_DRAFT = "send_to_psyke_draft"
I_GN_PANEL_FIELD = "send_to_panel_field"

GN_FIELD_CHOICES = (
    ("visual_description", "Visual"),
    ("caption", "Caption"),
    ("dialogue", "Dialogue"),
    ("sfx", "SFX"),
    ("notes", "Notes"),
)

AI_UNAVAILABLE = ("AI text operation unavailable. Configure an AI provider "
                  "or use rule-based cleanup.")
NO_SELECTION = "Select text first."
NO_SOURCE = "Select a transcript segment first."
STALE_PREVIEW = ("Target changed since preview. Regenerate preview before "
                 "applying.")
_REASON_OUTLINE = "Outline voice target not available yet."


@dataclass
class VoiceIntent:
    id: str
    type: str
    label: str
    enabled: bool
    requires_ai: bool = False
    requires_confirmation: bool = True   # always — preview-first by design
    reason_if_disabled: str = ""
    target_type: str = ""
    target_ref: tuple | None = None
    source_transcript_segment_ids: list[str] = field(default_factory=list)


@dataclass
class IntentPreview:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    intent_id: str = ""
    intent_type: str = ""
    project_id: int = 0
    created_at: float = field(default_factory=time.time)
    target_summary: str = ""
    before_text: str | None = None
    after_text: str | None = None
    diff: str | None = None
    created_note_preview: dict | None = None
    created_psyke_entry_preview: dict | None = None
    risk_level: str = "low"
    can_apply: bool = False
    reason_if_blocked: str = ""
    # Validation payload (apply re-checks against the live target).
    commit_target_id: str = ""
    gn_ref: tuple | None = None
    gn_field: str = ""
    source_segment_ids: list[str] = field(default_factory=list)


# ===========================================================================
# Rule-based cleanup (no AI, never fabricates)
# ===========================================================================

_SPOKEN_PUNCT = (
    (r"\bnew paragraph\b", "\n\n"),
    (r"\bnew line\b", "\n"),
    (r"\bcomma\b", ","),
    (r"\bperiod\b", "."),
    (r"\bfull stop\b", "."),
    (r"\bquestion mark\b", "?"),
    (r"\bexclamation (?:mark|point)\b", "!"),
    (r"\bsemicolon\b", ";"),
    (r"\bcolon\b", ":"),
    (r"\bopen quote\b", "“"),
    (r"\bclose quote\b", "”"),
)


def rule_based_cleanup(text: str, *, spoken_punctuation: bool = True) -> str:
    """Conservative local cleanup: whitespace, capitalization, optional
    spoken punctuation, final period. Never adds content."""
    out = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if spoken_punctuation:
        for pattern, repl in _SPOKEN_PUNCT:
            out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
        # Punctuation tokens leave a stray space behind: "word ," -> "word,"
        out = re.sub(r"\s+([,.;:!?])", r"\1", out)
        out = re.sub(r"([“])\s+", r"\1", out)
        out = re.sub(r"\s+([”])", r"\1", out)
    # Normalize space runs per line; collapse 3+ newlines; trim.
    out = "\n".join(re.sub(r"[ \t]+", " ", ln).strip()
                    for ln in out.split("\n"))
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    if not out:
        return ""
    # Capitalize the first letter and letters after sentence enders.
    out = re.sub(r"(^|[.!?]\s+)([a-z])",
                 lambda m: m.group(1) + m.group(2).upper(), out)
    if out[-1].isalnum():
        out += "."
    return out


def _diff(before: str, after: str) -> str:
    lines = difflib.unified_diff((before or "").splitlines(),
                                 (after or "").splitlines(),
                                 fromfile="before", tofile="after",
                                 lineterm="")
    return "\n".join(lines)


# ===========================================================================
# Helpers
# ===========================================================================

def _editor_selection(ctx: VoiceCommitContext) -> tuple[object, str]:
    """(editor, selected_text) — read-only; '' when nothing usable."""
    if ctx.active_editor_getter is None:
        return None, ""
    try:
        editor = ctx.active_editor_getter()
        cursor = editor.textCursor()
        text = cursor.selectedText().replace(" ", "\n")
        return editor, text
    except Exception:
        return None, ""


def _ai(ctx: VoiceCommitContext, prompt: str) -> str:
    fn = getattr(ctx, "ai_complete", None)
    if fn is None:
        return ""
    try:
        return (fn(prompt) or "").strip()
    except Exception:
        return ""


def _title(text: str) -> str:
    head = " ".join((text or "").split())[:40].strip()
    return f"Voice note — {head}" if head else "Voice note"


# ===========================================================================
# API
# ===========================================================================

def get_available_voice_intents(ctx: VoiceCommitContext) -> list[VoiceIntent]:
    """List the fixed intent allowlist for this context. Read-only."""
    mode = (ctx.writing_mode or "novel").lower()
    has_ai = getattr(ctx, "ai_complete", None) is not None
    _editor, selection = _editor_selection(ctx)
    intents = [
        VoiceIntent(id=I_CLEANUP, type=I_CLEANUP,
                    label="Clean up transcript (rule-based)", enabled=True),
        VoiceIntent(id=I_INSERT_CLEANED, type=I_INSERT_CLEANED,
                    label="Insert cleaned transcript (chosen target)",
                    enabled=True),
        VoiceIntent(
            id=I_REWRITE_SELECTION, type=I_REWRITE_SELECTION,
            label="Rewrite selected text (AI)", requires_ai=True,
            enabled=bool(has_ai and selection),
            reason_if_disabled=("" if (has_ai and selection)
                                else (AI_UNAVAILABLE if not has_ai
                                      else NO_SELECTION))),
        VoiceIntent(
            id=I_SUMMARIZE_TO_NOTE, type=I_SUMMARIZE_TO_NOTE,
            label="Summarize to Note (AI)", requires_ai=True,
            enabled=has_ai,
            reason_if_disabled="" if has_ai else AI_UNAVAILABLE),
        VoiceIntent(id=I_OUTLINE_DRAFT, type=I_OUTLINE_DRAFT,
                    label="Send to Outline draft item", enabled=False,
                    reason_if_disabled=_REASON_OUTLINE),
        VoiceIntent(id=I_PSYKE_DRAFT, type=I_PSYKE_DRAFT,
                    label="Send to PSYKE draft entry (chosen type)",
                    enabled=True),
    ]
    if mode == "graphic_novel":
        from logosforge.voice.commit_router import _gn_panel_exists
        panel_ok = _gn_panel_exists(ctx)
        intents.append(VoiceIntent(
            id=I_GN_PANEL_FIELD, type=I_GN_PANEL_FIELD,
            label="Send to selected Panel field (chosen field)",
            enabled=panel_ok,
            reason_if_disabled="" if panel_ok else "Select a Panel first.",
            target_ref=ctx.gn_panel_ref if panel_ok else None))
    return intents


def validate_voice_intent(intent_id: str,
                          ctx: VoiceCommitContext) -> tuple[bool, str]:
    for intent in get_available_voice_intents(ctx):
        if intent.id == intent_id:
            return ((True, "") if intent.enabled
                    else (False, intent.reason_if_disabled
                          or "Intent unavailable."))
    return False, "Intent unavailable."


def build_intent_preview(intent_id: str, source_text: str,
                         ctx: VoiceCommitContext, *,
                         commit_target_id: str = "",
                         source_segment_ids: list[str] | None = None,
                         use_ai_cleanup: bool = False) -> IntentPreview:
    """Build the preview for one intent. NEVER mutates anything."""
    preview = IntentPreview(intent_id=intent_id, intent_type=intent_id,
                            project_id=ctx.project_id,
                            source_segment_ids=list(source_segment_ids or []))
    ok, reason = validate_voice_intent(intent_id, ctx)
    if not ok:
        preview.reason_if_blocked = reason
        return preview
    text = (source_text or "").strip()

    if intent_id == I_CLEANUP:
        if not text:
            preview.reason_if_blocked = NO_SOURCE
            return preview
        cleaned = (
            _ai(ctx, "Clean up the following dictated text: fix punctuation "
                     "and capitalization only. Do not add or remove content. "
                     "Return ONLY the cleaned text.\n\n" + text)
            if use_ai_cleanup else rule_based_cleanup(text))
        if use_ai_cleanup and not cleaned:
            preview.reason_if_blocked = AI_UNAVAILABLE
            return preview
        if not cleaned:
            preview.reason_if_blocked = "Nothing left after cleanup."
            return preview
        preview.before_text, preview.after_text = text, cleaned
        preview.diff = _diff(text, cleaned)
        preview.target_summary = "Transcript segment text (no project change)"
        preview.can_apply = True
        return preview

    if intent_id == I_INSERT_CLEANED:
        if not text:
            preview.reason_if_blocked = NO_SOURCE
            return preview
        cleaned = rule_based_cleanup(text)
        if not cleaned:
            preview.reason_if_blocked = "Nothing left after cleanup."
            return preview
        targets = {t.id: t for t in get_available_voice_commit_targets(ctx)}
        target = targets.get(commit_target_id)
        if target is None or not target.enabled:
            preview.reason_if_blocked = (
                target.reason_if_disabled if target else "Pick a target.")
            return preview
        preview.before_text, preview.after_text = text, cleaned
        preview.diff = _diff(text, cleaned)
        preview.commit_target_id = commit_target_id
        preview.target_summary = f"Commit to: {target.label}"
        preview.can_apply = True
        return preview

    if intent_id == I_REWRITE_SELECTION:
        _editor, selection = _editor_selection(ctx)
        if not selection:
            preview.reason_if_blocked = NO_SELECTION
            return preview
        instruction = text or "Rewrite this text more clearly."
        after = _ai(ctx, "Rewrite the following text according to this "
                         "instruction. Return ONLY the rewritten text, no "
                         "preamble.\n\nInstruction: " + instruction
                         + "\n\nText:\n" + selection)
        if not after:
            preview.reason_if_blocked = "AI returned no text."
            return preview
        preview.before_text, preview.after_text = selection, after
        preview.diff = _diff(selection, after)
        preview.target_summary = "Replace the selected text in the editor"
        preview.risk_level = "medium"
        preview.can_apply = True
        return preview

    if intent_id == I_SUMMARIZE_TO_NOTE:
        _editor, selection = _editor_selection(ctx)
        source = selection or text
        if not source:
            preview.reason_if_blocked = NO_SOURCE
            return preview
        summary = _ai(ctx, "Summarize the following text in a few sentences. "
                           "Return ONLY the summary.\n\n" + source)
        if not summary:
            preview.reason_if_blocked = "AI returned no text."
            return preview
        preview.created_note_preview = {"title": _title(summary),
                                        "content": summary}
        preview.after_text = summary
        preview.target_summary = "Create a new Note"
        preview.can_apply = True
        return preview

    if intent_id == I_PSYKE_DRAFT:
        if not text:
            preview.reason_if_blocked = NO_SOURCE
            return preview
        entry_type = (ctx.psyke_entry_type or "other").lower()
        from logosforge.voice.commit_router import PSYKE_ENTRY_TYPES
        if entry_type not in PSYKE_ENTRY_TYPES:
            entry_type = "other"          # user-chosen only, never guessed
        preview.created_psyke_entry_preview = {
            "name": _title(text), "entry_type": entry_type, "notes": text}
        preview.after_text = text
        preview.target_summary = f"Create a PSYKE draft entry ({entry_type})"
        preview.can_apply = True
        return preview

    if intent_id == I_GN_PANEL_FIELD:
        if not text:
            preview.reason_if_blocked = NO_SOURCE
            return preview
        field_name = getattr(ctx, "gn_field_choice", "") or "visual_description"
        if field_name not in dict(GN_FIELD_CHOICES):
            field_name = "visual_description"
        scene_id, page_idx, panel_idx = ctx.gn_panel_ref
        from logosforge import graphic_novel_blocks as gnb
        script = gnb.load_scene_script(ctx.db, scene_id)
        try:
            current = getattr(script.pages[page_idx].panels[panel_idx],
                              field_name, "")
        except IndexError:
            preview.reason_if_blocked = "Select a Panel first."
            return preview
        after = f"{current}\n{text}" if (current or "").strip() else text
        preview.before_text, preview.after_text = current, after
        preview.diff = _diff(current, after)
        preview.gn_ref = (scene_id, page_idx, panel_idx)
        preview.gn_field = field_name
        preview.target_summary = (
            f"Panel {panel_idx + 1} on Page {page_idx + 1} — "
            f"{dict(GN_FIELD_CHOICES)[field_name]}")
        preview.can_apply = True
        return preview

    preview.reason_if_blocked = "Intent unavailable."
    return preview


def validate_intent_preview(preview: IntentPreview,
                            ctx: VoiceCommitContext) -> tuple[bool, str]:
    """Re-check a preview against the LIVE state (read-only)."""
    if preview is None or not preview.can_apply:
        return False, (preview.reason_if_blocked if preview
                       else "No preview.") or "No preview."
    if preview.project_id != ctx.project_id:
        return False, STALE_PREVIEW
    if preview.intent_type == I_REWRITE_SELECTION:
        _editor, selection = _editor_selection(ctx)
        if selection != (preview.before_text or ""):
            return False, STALE_PREVIEW
    if preview.intent_type == I_GN_PANEL_FIELD:
        try:
            from logosforge import graphic_novel_blocks as gnb
            scene_id, page_idx, panel_idx = preview.gn_ref
            script = gnb.load_scene_script(ctx.db, scene_id)
            current = getattr(script.pages[page_idx].panels[panel_idx],
                              preview.gn_field, None)
        except Exception:
            return False, STALE_PREVIEW
        if current != (preview.before_text or ""):
            return False, STALE_PREVIEW
    if preview.intent_type == I_INSERT_CLEANED:
        targets = {t.id: t for t in get_available_voice_commit_targets(ctx)}
        target = targets.get(preview.commit_target_id)
        if target is None or not target.enabled:
            return False, STALE_PREVIEW
    return True, ""


def apply_intent_preview(preview: IntentPreview, ctx: VoiceCommitContext
                         ) -> tuple[bool, str, CommitOperation | None]:
    """Apply ONE confirmed preview. Mutates only after re-validation."""
    ok, reason = validate_intent_preview(preview, ctx)
    if not ok:
        return False, reason, None
    kind = preview.intent_type

    if kind == I_CLEANUP:
        # Transcript-only operation: the panel updates the segment text; the
        # project itself is untouched (and stays un-dirtied).
        return True, "Cleaned text ready.", None

    if kind == I_INSERT_CLEANED:
        return commit_transcript_op(preview.after_text or "",
                                    preview.commit_target_id, ctx)

    if kind == I_REWRITE_SELECTION:
        editor, _selection = _editor_selection(ctx)
        if editor is None:
            return False, STALE_PREVIEW, None
        try:
            cursor = editor.textCursor()
            cursor.insertText(preview.after_text or "")  # replaces selection
            op = CommitOperation(
                target_id=I_REWRITE_SELECTION, label="Rewrite selected text",
                project_id=ctx.project_id, kind="cursor", editor=editor,
                inserted_text=preview.after_text or "")
            op.doc_revision = editor.document().revision()
            return True, "Selected text rewritten.", op
        except Exception:
            return False, STALE_PREVIEW, None

    if kind == I_SUMMARIZE_TO_NOTE:
        data = preview.created_note_preview or {}
        note = ctx.db.create_note(ctx.project_id,
                                  data.get("title") or "Voice note",
                                  content=data.get("content") or "")
        op = CommitOperation(target_id=I_SUMMARIZE_TO_NOTE,
                             label="Summarize to Note",
                             project_id=ctx.project_id, kind="note",
                             created_id=note.id,
                             created_text=data.get("content") or "")
        return True, "Note created.", op

    if kind == I_PSYKE_DRAFT:
        data = preview.created_psyke_entry_preview or {}
        entry = ctx.db.create_psyke_entry(
            ctx.project_id, data.get("name") or "Voice draft",
            entry_type=data.get("entry_type") or "other",
            notes=data.get("notes") or "")
        op = CommitOperation(target_id=I_PSYKE_DRAFT,
                             label="PSYKE draft entry",
                             project_id=ctx.project_id, kind="psyke",
                             created_id=entry.id,
                             created_text=data.get("notes") or "")
        return True, "PSYKE draft entry created.", op

    if kind == I_GN_PANEL_FIELD:
        from logosforge import graphic_novel_outline as gno
        scene_id, page_idx, panel_idx = preview.gn_ref
        done = gno.set_panel_field(ctx.db, scene_id, page_idx, panel_idx,
                                   preview.gn_field,
                                   preview.after_text or "")
        if not done:
            return False, STALE_PREVIEW, None
        op = CommitOperation(target_id=I_GN_PANEL_FIELD,
                             label="Panel field update",
                             project_id=ctx.project_id, kind="gn_field",
                             gn_ref=preview.gn_ref,
                             gn_field=preview.gn_field,
                             gn_prev_value=preview.before_text or "",
                             gn_new_value=preview.after_text or "")
        return True, "Panel field updated.", op

    return False, "Intent unavailable.", None


def cancel_voice_intent(preview: IntentPreview | None) -> None:
    """Cancel = drop the preview. Nothing was mutated; nothing to clean."""
    return None
