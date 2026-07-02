"""Voice transcript history — local, session-only review layer (Phase 3).

Tracks the transcript segments of the current voice session so the user can
**inspect, edit, select, merge, split, retry, discard and commit** them
explicitly. Pure logic, no Qt; the voice panel renders it.

Local-first rules:

* everything lives in memory for the session only — nothing is persisted,
  no telemetry, no uploads; segment audio (raw PCM, for *Retry
  transcription*) never touches disk and is dropped on discard/clear;
* every segment records the project (and writing mode) it was captured in —
  commits into a different project are blocked upstream by the Commit
  Router's project check;
* nothing here mutates the project: committing goes through the Voice
  Commit Router only, and this module merely records the outcome.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from logosforge.voice.types import TranscriptSegment

# Segment lifecycle states (§2).
S_PENDING = "pending"
S_EDITED = "edited"
S_COMMITTED = "committed"
S_DISCARDED = "discarded"
S_FAILED = "failed"
S_CORRECTED = "corrected"          # glossary corrections applied (Phase 7)

_EDITABLE = (S_PENDING, S_EDITED, S_FAILED, S_CORRECTED)
_COMMITTABLE = (S_PENDING, S_EDITED, S_CORRECTED)

RETRY_UNAVAILABLE = "Audio segment no longer available."
PROJECT_MISMATCH = ("This transcript was captured in another project. "
                    "Switch back or explicitly retarget.")


@dataclass
class VoiceSession:
    """One dictation session (§3). No secrets — model label only."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    project_id: int = 0
    started_at: float = field(default_factory=time.time)
    stopped_at: float | None = None
    status: str = "active"               # active | stopped | stale
    backend: str = ""
    model_label: str = ""
    language: str = ""


@dataclass
class HistoryEntry:
    """One reviewable transcript segment in the session history."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str = ""
    project_id_at_capture: int = 0
    writing_mode_at_capture: str = ""
    text: str = ""
    original_text: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    language: str = ""
    source: str = "local_whisper"
    is_final: bool = True
    status: str = S_PENDING
    committed_target: str = ""
    committed_at: float | None = None
    commit_operation_id: str = ""
    duration_ms: int = 0
    confidence: float | None = None
    error: str = ""
    # Provenance for merge/split.
    merged_from: list[str] = field(default_factory=list)
    split_from: str = ""
    # Voice glossary (Phase 7): pending correction suggestions (local).
    corrections: list = field(default_factory=list)
    # Billy Voice Bridge (Phase 5): text-only; never audio, never secrets.
    sent_to_billy: bool = False
    billy_proposal_id: str = ""
    billy_state: str = ""                # "" | proposed | applied | cancelled
    # Session-only local audio for Retry (never persisted, never uploaded).
    audio_bytes: bytes | None = field(default=None, repr=False)
    sample_rate: int = 16000
    audio_retention_policy: str = "session"

    def preview(self, width: int = 48) -> str:
        flat = " ".join((self.text or "").split())
        return flat[:width] + ("…" if len(flat) > width else "")


class VoiceTranscriptHistory:
    """The current session's segments + the safe operations over them."""

    def __init__(self) -> None:
        self.session: VoiceSession | None = None
        self.entries: list[HistoryEntry] = []
        self.last_commit_op = None       # router CommitOperation (undo target)

    # ------------------------------------------------------------- session
    def start_session(self, project_id: int, *, backend: str = "",
                      model_label: str = "", language: str = ""
                      ) -> VoiceSession:
        """One active session at a time; a running one is stopped first.
        Existing entries are kept (stopping/starting never clears history)."""
        if self.session is not None and self.session.status == "active":
            self.end_session()
        self.session = VoiceSession(project_id=project_id, backend=backend,
                                    model_label=model_label,
                                    language=language)
        return self.session

    def end_session(self) -> None:
        if self.session is not None and self.session.stopped_at is None:
            self.session.stopped_at = time.time()
            if self.session.status == "active":
                self.session.status = "stopped"

    def mark_session_stale(self) -> None:
        """Project switched: history stays visible but is from elsewhere."""
        if self.session is not None:
            self.session.status = "stale"

    # -------------------------------------------------------------- counters
    @property
    def segment_count(self) -> int:
        return len(self.entries)

    @property
    def committed_count(self) -> int:
        return sum(1 for e in self.entries if e.status == S_COMMITTED)

    @property
    def error_count(self) -> int:
        return sum(1 for e in self.entries if e.status == S_FAILED)

    # --------------------------------------------------------------- entries
    def add_final_segment(self, seg: TranscriptSegment, *, project_id: int,
                          writing_mode: str = "") -> HistoryEntry:
        if self.session is None or self.session.status != "active":
            self.start_session(project_id)
        entry = HistoryEntry(
            session_id=self.session.id,
            project_id_at_capture=project_id,
            writing_mode_at_capture=writing_mode,
            text=seg.text or "",
            original_text=seg.text or "",
            language=seg.language or "",
            source=seg.source or "local_whisper",
            is_final=bool(seg.is_final),
            duration_ms=int((seg.duration_s or 0.0) * 1000),
            confidence=seg.confidence,
            audio_bytes=seg.audio_bytes,
            sample_rate=int(seg.sample_rate or 16000),
        )
        self.entries.append(entry)
        return entry

    def get(self, entry_id: str) -> HistoryEntry | None:
        return next((e for e in self.entries if e.id == entry_id), None)

    def visible_entries(self) -> list[HistoryEntry]:
        return list(self.entries)

    # --------------------------------------------------------------- editing
    def edit(self, entry_id: str, new_text: str) -> bool:
        """Manual correction (never automatic). Keeps ``original_text``."""
        entry = self.get(entry_id)
        if entry is None or entry.status not in _EDITABLE:
            return False
        entry.text = new_text
        entry.status = (S_PENDING if new_text == entry.original_text
                        else S_EDITED)
        entry.updated_at = time.time()
        return True

    def apply_corrections(self, entry_id: str, corrected_text: str) -> bool:
        """Glossary corrections applied to the TRANSCRIPT text only (the
        document is reached solely via the Commit Router on commit)."""
        entry = self.get(entry_id)
        if entry is None or entry.status not in _EDITABLE:
            return False
        entry.text = corrected_text
        entry.status = (S_PENDING if corrected_text == entry.original_text
                        else S_CORRECTED)
        entry.updated_at = time.time()
        return True

    def restore_original(self, entry_id: str) -> bool:
        entry = self.get(entry_id)
        if entry is None or entry.status not in _EDITABLE:
            return False
        entry.text = entry.original_text
        entry.status = S_PENDING
        entry.updated_at = time.time()
        return True

    def discard(self, entry_id: str) -> bool:
        entry = self.get(entry_id)
        if entry is None or entry.status == S_COMMITTED:
            return False
        entry.status = S_DISCARDED
        entry.audio_bytes = None          # retention: dropped immediately
        entry.updated_at = time.time()
        return True

    def clear_uncommitted(self) -> int:
        """Remove pending/edited/failed entries (audio dropped with them)."""
        keep, removed = [], 0
        for entry in self.entries:
            if entry.status in (S_COMMITTED, S_DISCARDED):
                keep.append(entry)
            else:
                entry.audio_bytes = None
                removed += 1
        self.entries = keep
        return removed

    def clear_finished(self) -> int:
        """Remove committed/discarded entries from the visible history."""
        keep = [e for e in self.entries
                if e.status not in (S_COMMITTED, S_DISCARDED)]
        removed = len(self.entries) - len(keep)
        self.entries = keep
        return removed

    def clear_all(self) -> None:
        for entry in self.entries:
            entry.audio_bytes = None
        self.entries = []
        self.end_session()
        self.session = None
        self.last_commit_op = None

    # ------------------------------------------------------------ committing
    def committable(self, entry: HistoryEntry) -> bool:
        return (entry.status in _COMMITTABLE
                and bool((entry.text or "").strip()))

    def concat_text(self, entry_ids: list[str]) -> str:
        """Selected segments joined in VISIBLE order (edited text, like the
        live preview joins finalized segments — single spaces)."""
        chosen = [e for e in self.entries
                  if e.id in set(entry_ids) and self.committable(e)]
        return " ".join((e.text or "").strip() for e in chosen).strip()

    def check_same_project(self, entry_ids: list[str],
                           project_id: int) -> tuple[bool, str]:
        for entry in self.entries:
            if entry.id in set(entry_ids) \
                    and entry.project_id_at_capture != project_id:
                return False, PROJECT_MISMATCH
        return True, ""

    def mark_committed(self, entry_ids: list[str], target_id: str,
                       op_id: str = "") -> None:
        now = time.time()
        for entry in self.entries:
            if entry.id in set(entry_ids) and entry.status in _COMMITTABLE:
                entry.status = S_COMMITTED
                entry.committed_target = target_id
                entry.committed_at = now
                entry.commit_operation_id = op_id
                entry.audio_bytes = None  # no longer needed; keep it local
                entry.updated_at = now

    def mark_failed(self, entry_id: str, error: str) -> None:
        entry = self.get(entry_id)
        if entry is not None and entry.status in _COMMITTABLE:
            entry.status = S_FAILED
            entry.error = error
            entry.updated_at = time.time()

    # ------------------------------------------------------------ merge/split
    def merge(self, entry_ids: list[str]) -> HistoryEntry | None:
        """Merge ADJACENT uncommitted segments (same session+project) into
        one. Originals are replaced; provenance kept in ``merged_from``."""
        wanted = set(entry_ids)
        positions = [i for i, e in enumerate(self.entries) if e.id in wanted]
        if len(positions) < 2:
            return None
        chosen = [self.entries[i] for i in positions]
        if positions != list(range(positions[0],
                                   positions[0] + len(positions))):
            return None                   # not adjacent in visible order
        if any(e.status not in _COMMITTABLE for e in chosen):
            return None                   # committed/discarded never merge
        if len({e.session_id for e in chosen}) != 1 \
                or len({e.project_id_at_capture for e in chosen}) != 1:
            return None
        merged = HistoryEntry(
            session_id=chosen[0].session_id,
            project_id_at_capture=chosen[0].project_id_at_capture,
            writing_mode_at_capture=chosen[0].writing_mode_at_capture,
            text=" ".join((e.text or "").strip() for e in chosen).strip(),
            original_text=" ".join((e.original_text or "").strip()
                                   for e in chosen).strip(),
            language=chosen[0].language,
            merged_from=[e.id for e in chosen],
        )
        merged.status = (S_PENDING if merged.text == merged.original_text
                         else S_EDITED)
        for entry in chosen:              # audio cannot be merged — drop it
            entry.audio_bytes = None
        self.entries[positions[0]:positions[0] + len(positions)] = [merged]
        return merged

    def split(self, entry_id: str, index: int) -> tuple | None:
        """Split one uncommitted segment's TEXT at *index* into two segments.
        Audio is not split (Retry becomes unavailable for both halves)."""
        entry = self.get(entry_id)
        if entry is None or entry.status not in _COMMITTABLE:
            return None
        text = entry.text or ""
        head, tail = text[:index].strip(), text[index:].strip()
        if not head or not tail:
            return None                   # both halves must be non-empty
        pos = self.entries.index(entry)
        common = dict(
            session_id=entry.session_id,
            project_id_at_capture=entry.project_id_at_capture,
            writing_mode_at_capture=entry.writing_mode_at_capture,
            language=entry.language, split_from=entry.id,
        )
        first = HistoryEntry(text=head, original_text=head, **common)
        second = HistoryEntry(text=tail, original_text=tail, **common)
        self.entries[pos:pos + 1] = [first, second]
        return first, second

    # ----------------------------------------------------------------- retry
    def can_retry(self, entry: HistoryEntry) -> tuple[bool, str]:
        if entry.status not in _EDITABLE:
            return False, "Only uncommitted segments can be retried."
        if not entry.audio_bytes:
            return False, RETRY_UNAVAILABLE
        return True, ""

    def retry_transcription(self, entry_id: str,
                            transcriber) -> tuple[bool, str]:
        """Re-run the LOCAL transcriber on the kept audio. The new text
        replaces the segment's text (original_text/provenance kept); a
        failure leaves the previous transcript untouched."""
        entry = self.get(entry_id)
        if entry is None:
            return False, "Segment not found."
        ok, reason = self.can_retry(entry)
        if not ok:
            return False, reason
        seg = transcriber.transcribe(entry.audio_bytes,
                                     sample_rate=entry.sample_rate,
                                     language=entry.language or None)
        if seg.error or seg.is_empty():
            return False, seg.error or "Retry produced no transcript."
        entry.text = seg.text
        entry.status = (S_PENDING if entry.text == entry.original_text
                        else S_EDITED)
        entry.updated_at = time.time()
        return True, "Transcription retried."
