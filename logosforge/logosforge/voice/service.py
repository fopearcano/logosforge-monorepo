"""VoiceRoomService — headless, frontend-agnostic API for Dexter's Room.

This is the **canonical voice API surface** the API layer (and any frontend —
the existing PySide6 panel today, an Electron/React Dexter tomorrow) consumes,
so that no frontend re-derives voice behaviour. It is **pure Python (no Qt)**
and every method returns **JSON-safe dicts** (see :mod:`serialization`).

What it owns:

* backend status / diagnostics;
* transcription (stateless) and optional **server-side segmentation** — reusing
  the pure-Python :class:`AudioBuffer` so the silence/segment behaviour stays
  canonical regardless of frontend;
* the session transcript **history** (add / edit / merge / split / retry / …);
* glossary correction suggestions;
* the **Intent** and **Billy** preview→apply flows;
* commit-target listing and commit.

What it does NOT own (these are frontend concerns, by design):

* **microphone capture** — the frontend captures audio and sends PCM here;
* **the text editor** — cursor/editor commits return the prepared text under
  ``inserted_text`` for the frontend to insert; only DB targets (Note / PSYKE)
  are committed server-side.

The caller injects the core ``db`` and, optionally, an ``ai_complete`` callable
(the app's existing provider) used by the AI-backed Intent/Billy actions; with
no provider those actions degrade gracefully to blocked/chat-only.

Audio model — the facade supports both:

* **Option A (frontend segments):** call :meth:`transcribe_segment` with a
  finalized PCM segment; it transcribes and records a history entry.
* **Option B (core segments):** stream chunks to :meth:`feed_chunk`; the core
  segmenter finalizes on silence/max-duration and records the entry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from logosforge.voice import billy_bridge as bb
from logosforge.voice import commit_router as cr
from logosforge.voice import glossary as vg
from logosforge.voice import intent_router as ir
from logosforge.voice import serialization as ser
from logosforge.voice import setup as vs
from logosforge.voice.audio_buffer import AudioBuffer
from logosforge.voice.commit_router import VoiceCommitContext
from logosforge.voice.history import VoiceTranscriptHistory
from logosforge.voice.transcriber import build_transcriber
from logosforge.voice.types import VoiceSettings


class VoiceRoomService:
    """Headless Dexter's Room API. One instance per dictation session/project."""

    def __init__(self, db, project_id: int, *, writing_mode: str = "novel",
                 settings: VoiceSettings | None = None,
                 ai_complete: Callable[[str], str] | None = None,
                 history: VoiceTranscriptHistory | None = None,
                 transcriber=None) -> None:
        self._db = db
        self._project_id = int(project_id)
        self._writing_mode = writing_mode or "novel"
        self._settings = settings or VoiceSettings()
        self._ai_complete = ai_complete
        # History and transcriber are injectable so this service can wrap an
        # existing session's state (e.g. share one history) rather than always
        # owning its own; otherwise it lazily builds them.
        self._history = history if history is not None else VoiceTranscriptHistory()
        self._transcriber = transcriber       # injected, or lazy in _transcriber_for
        self._buffer: AudioBuffer | None = None  # lazy (server-side segmenting)
        self._intent_previews: dict[str, ir.IntentPreview] = {}
        self._billy_proposals: dict[str, bb.BillyVoiceProposal] = {}
        self._corrections: dict[str, Any] = {}   # id -> CorrectionSuggestion
        self._last_op = None                  # last server-side commit, for undo

    # -- configuration ------------------------------------------------------
    def set_settings(self, settings: VoiceSettings) -> None:
        self._settings = settings
        self._transcriber = None
        self._buffer = None

    def set_project(self, project_id: int, *, writing_mode: str = "") -> None:
        if writing_mode:
            self._writing_mode = writing_mode
        if int(project_id) != self._project_id:
            self._project_id = int(project_id)
            self._history.mark_session_stale()   # never commit across projects

    def _transcriber_for(self):
        if self._transcriber is None:
            self._transcriber = build_transcriber(self._settings)
        return self._transcriber

    def _buffer_for(self) -> AudioBuffer:
        if self._buffer is None:
            s = self._settings
            self._buffer = AudioBuffer(
                s.sample_rate, silence_ms=s.silence_ms,
                max_segment_seconds=s.max_segment_seconds, channels=s.channels)
        return self._buffer

    # -- status -------------------------------------------------------------
    def backend_status(self) -> dict[str, Any]:
        return ser.backend_profile_to_dict(
            vs.build_backend_profile(self._settings))

    # -- transcription ------------------------------------------------------
    def transcribe(self, pcm: bytes, *, sample_rate: int | None = None,
                   language: str | None = None) -> dict[str, Any]:
        """Stateless STT of one PCM segment (no history). The raw capability."""
        seg = self._transcriber_for().transcribe(
            pcm, sample_rate=sample_rate or self._settings.sample_rate,
            language=language or self._settings.effective_language())
        return ser.transcript_to_dict(seg)

    def transcribe_segment(self, pcm: bytes) -> dict[str, Any] | None:
        """Option A: transcribe a finalized PCM segment and record it in
        history. Returns the history entry, or None for an empty/no-speech
        segment (nothing is recorded)."""
        return self._transcribe_and_record(pcm)

    def feed_chunk(self, pcm: bytes) -> dict[str, Any] | None:
        """Option B: stream a PCM chunk; returns a recorded history entry when
        the core segmenter finalizes one (silence / max duration), else None."""
        seg_bytes = self._buffer_for().feed(pcm)
        if seg_bytes is None:
            return None
        return self._transcribe_and_record(seg_bytes)

    def flush(self) -> dict[str, Any] | None:
        """Option B: finalize any buffered audio (e.g. on Stop)."""
        seg_bytes = self._buffer_for().flush()
        if seg_bytes is None:
            return None
        return self._transcribe_and_record(seg_bytes)

    def _transcribe_and_record(self, pcm: bytes) -> dict[str, Any] | None:
        if not pcm:
            return None
        seg = self._transcriber_for().transcribe(
            pcm, sample_rate=self._settings.sample_rate,
            language=self._settings.effective_language())
        if seg.error:
            return ser.transcript_to_dict(seg)   # surface the error; nothing recorded
        if seg.is_empty():
            return None                           # no speech: nothing to record
        seg.audio_bytes = pcm                     # session-only, for Retry
        seg.sample_rate = self._settings.sample_rate
        entry = self._history.add_final_segment(
            seg, project_id=self._project_id, writing_mode=self._writing_mode)
        return ser.history_entry_to_dict(entry)

    # -- history ------------------------------------------------------------
    def history(self) -> list[dict[str, Any]]:
        return [ser.history_entry_to_dict(e)
                for e in self._history.visible_entries()]

    def edit_segment(self, entry_id: str, text: str) -> dict[str, Any] | None:
        if not self._history.edit(entry_id, text):
            return None
        return self._entry_dict(entry_id)

    def merge_segments(self, entry_ids: list[str]) -> dict[str, Any] | None:
        entry = self._history.merge(list(entry_ids))
        return ser.history_entry_to_dict(entry) if entry is not None else None

    def split_segment(self, entry_id: str,
                      index: int) -> list[dict[str, Any]] | None:
        result = self._history.split(entry_id, index)
        if not result:
            return None
        return [ser.history_entry_to_dict(e) for e in result]

    def discard_segment(self, entry_id: str) -> bool:
        return self._history.discard(entry_id)

    def restore_segment(self, entry_id: str) -> bool:
        return self._history.restore_original(entry_id)

    def retry_segment(self, entry_id: str) -> dict[str, Any]:
        ok, message = self._history.retry_transcription(
            entry_id, self._transcriber_for())
        return {"ok": bool(ok), "message": message,
                "entry": self._entry_dict(entry_id)}

    def clear_uncommitted(self) -> int:
        return self._history.clear_uncommitted()

    def clear_finished(self) -> int:
        return self._history.clear_finished()

    def _entry_dict(self, entry_id: str) -> dict[str, Any] | None:
        entry = self._history.get(entry_id)
        return ser.history_entry_to_dict(entry) if entry is not None else None

    # -- glossary corrections ----------------------------------------------
    def suggest_corrections(self, text: str, *, spoken_punctuation: bool = True,
                            fuzzy: bool = False) -> list[dict[str, Any]]:
        suggestions = vg.suggest_transcript_corrections(
            self._db, self._project_id, text,
            spoken_punctuation=spoken_punctuation, fuzzy=fuzzy)
        self._corrections = {s.id: s for s in suggestions}
        return [ser.correction_to_dict(s) for s in suggestions]

    def apply_corrections(self, text: str,
                          suggestion_ids: list[str]) -> dict[str, Any]:
        chosen = [self._corrections[i] for i in suggestion_ids
                  if i in self._corrections]
        new_text = vg.apply_selected_corrections(text, chosen)
        return {"text": new_text, "applied_count": len(chosen)}

    # -- intents ------------------------------------------------------------
    def list_intents(self, ctx_fields: dict | None = None
                     ) -> list[dict[str, Any]]:
        ctx, _ = self._build_context(ctx_fields)
        return [ser.intent_to_dict(i)
                for i in ir.get_available_voice_intents(ctx)]

    def preview_intent(self, intent_id: str, source_text: str,
                       ctx_fields: dict | None = None, *,
                       commit_target_id: str = "",
                       source_segment_ids: list[str] | None = None
                       ) -> dict[str, Any]:
        ctx, _ = self._build_context(ctx_fields)
        preview = ir.build_intent_preview(
            intent_id, source_text, ctx, commit_target_id=commit_target_id,
            source_segment_ids=source_segment_ids)
        self._intent_previews[preview.id] = preview
        return ser.intent_preview_to_dict(preview)

    def apply_intent(self, preview_id: str,
                     ctx_fields: dict | None = None) -> dict[str, Any]:
        preview = self._intent_previews.get(preview_id)
        if preview is None:
            return {"applied": False, "message": "Unknown intent preview."}
        ctx, captured = self._build_context(ctx_fields)
        ok, message, op = ir.apply_intent_preview(preview, ctx)
        if ok and op is not None:
            self._last_op = op
        # Rule-based cleanup returns cleaned text on the preview, committing
        # nothing — hand it back for the frontend to use.
        text = preview.after_text if (ok and preview.intent_type == ir.I_CLEANUP) \
            else None
        return self._apply_result(ok, message, captured,
                                  extra={"cleaned_text": text} if text else None)

    # -- Billy --------------------------------------------------------------
    def billy_operations(self, ctx_fields: dict | None = None
                         ) -> list[dict[str, Any]]:
        ctx, _ = self._build_context(ctx_fields)
        return [ser.billy_operation_to_dict(o)
                for o in bb.get_available_billy_operations(ctx)]

    def generate_billy(self, operation: str, transcript_text: str,
                       ctx_fields: dict | None = None, *,
                       source_segment_ids: list[str] | None = None
                       ) -> dict[str, Any]:
        ctx, _ = self._build_context(ctx_fields)
        proposal = bb.request_billy_proposal(
            operation, transcript_text, ctx,
            source_segment_ids=source_segment_ids)
        self._billy_proposals[proposal.id] = proposal
        return ser.billy_proposal_to_dict(proposal)

    def apply_billy(self, proposal_id: str,
                    ctx_fields: dict | None = None) -> dict[str, Any]:
        proposal = self._billy_proposals.get(proposal_id)
        if proposal is None:
            return {"applied": False, "message": "Unknown Billy proposal."}
        ctx, captured = self._build_context(ctx_fields)
        ok, message, op = bb.apply_billy_voice_proposal(proposal, ctx)
        if ok and op is not None:
            self._last_op = op
        return self._apply_result(ok, message, captured)

    # -- commit -------------------------------------------------------------
    def commit_targets(self, ctx_fields: dict | None = None
                       ) -> list[dict[str, Any]]:
        ctx, _ = self._build_context(ctx_fields)
        return [ser.commit_target_to_dict(t)
                for t in cr.get_available_voice_commit_targets(ctx)]

    def commit(self, text: str, target_id: str,
               ctx_fields: dict | None = None) -> dict[str, Any]:
        ctx, captured = self._build_context(ctx_fields)
        ok, message, op = cr.commit_transcript_op(text, target_id, ctx)
        if ok and op is not None:
            self._last_op = op
        return self._apply_result(ok, message, captured)

    # -- undo (server-side commits: Note / PSYKE / GN field) ----------------
    def can_undo(self) -> dict[str, Any]:
        """Whether the last commit can be undone server-side. Cursor/editor
        inserts return False here — the frontend owns its own editor undo."""
        ctx, _ = self._build_context(None)
        ok, reason = cr.can_undo(self._last_op, ctx)
        return {"can_undo": bool(ok), "reason": reason}

    def undo_last(self) -> dict[str, Any]:
        ctx, _ = self._build_context(None)
        ok, message = cr.undo_commit(self._last_op, ctx)
        if ok:
            self._last_op = None
        return {"undone": bool(ok), "message": message}

    # -- internals ----------------------------------------------------------
    def _build_context(self, fields: dict | None
                       ) -> tuple[VoiceCommitContext, list[str]]:
        """Build a commit context from serializable fields, with a capturing
        cursor sink: editor/cursor commits append the text to ``captured``
        (returned to the frontend to insert) instead of mutating a widget; DB
        targets (Note/PSYKE) write through ``db`` server-side as usual."""
        fields = fields or {}
        captured: list[str] = []

        def _capture(text: str) -> bool:
            captured.append(text)
            return True

        gn_ref = fields.get("gn_panel_ref")
        ctx = VoiceCommitContext(
            db=self._db,
            project_id=self._project_id,
            writing_mode=fields.get("writing_mode", self._writing_mode),
            has_active_editor=bool(fields.get("has_active_editor", True)),
            insert_at_cursor=_capture,
            gn_panel_ref=tuple(gn_ref) if gn_ref else None,
            psyke_entry_type=fields.get("psyke_entry_type", "other"),
            character_name=fields.get("character_name", ""),
            gn_field_choice=fields.get("gn_field_choice", "visual_description"),
            ai_complete=self._ai_complete,
            transcript_project_id=fields.get("transcript_project_id"),
        )
        return ctx, captured

    @staticmethod
    def _apply_result(ok: bool, message: str, captured: list[str],
                      extra: dict | None = None) -> dict[str, Any]:
        """Uniform apply/commit result. ``inserted_text`` present => the
        frontend should insert it at its cursor; absent => committed
        server-side (e.g. a Note/PSYKE entry was created)."""
        result: dict[str, Any] = {"applied": bool(ok), "message": message}
        if captured:
            result["inserted_text"] = captured[-1]
        if extra:
            result.update(extra)
        return result
