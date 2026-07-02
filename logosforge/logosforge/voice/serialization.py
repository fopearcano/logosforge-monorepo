"""JSON-safe serialization of the Voice (Dexter's Room) data contracts.

This is the wire shape a frontend consumes through the API layer: every voice
domain object becomes a plain ``dict`` of JSON-safe primitives. Two things are
deliberately **never** on the wire:

* ``audio_bytes`` — raw local PCM (audio stays on-device; history exposes only
  ``has_audio`` so a frontend knows whether "Retry" is possible);
* runtime callables (``insert_at_cursor``, ``ai_complete``, ``db``) — those are
  server-side wiring, not data.

Keeping serialization here (rather than as methods on the dataclasses) keeps the
domain model clean and makes the contract explicit and reviewable in one place.
``(scene, page, panel)`` tuples are emitted as lists so they round-trip JSON.
"""

from __future__ import annotations

from typing import Any


def _ref(value) -> list | None:
    """A panel ``(scene, page, panel)``-style tuple -> list, or None."""
    return list(value) if value is not None else None


def transcript_to_dict(seg) -> dict[str, Any]:
    return {
        "id": seg.id,
        "text": seg.text,
        "is_final": bool(seg.is_final),
        "is_empty": seg.is_empty(),
        "language": seg.language,
        "duration_s": seg.duration_s,
        "error": seg.error,
        "source": seg.source,
        "confidence": seg.confidence,
        "created_at": seg.created_at,
        "committed": bool(seg.committed),
        "committed_target": seg.committed_target,
        "committed_at": seg.committed_at,
        "sample_rate": seg.sample_rate,
        "selected_language_code": seg.selected_language_code,
        "detected_language_code": seg.detected_language_code,
        "language_source": seg.language_source,
        "project_language_code": seg.project_language_code,
        "dexter_language_mode": seg.dexter_language_mode,
    }


def correction_to_dict(s) -> dict[str, Any]:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "original_text": s.original_text,
        "replacement_text": s.replacement_text,
        "start_offset": s.start_offset,
        "end_offset": s.end_offset,
        "source_term_id": s.source_term_id,
        "source": s.source,
        "reason": s.reason,
        "confidence": s.confidence,
        "applied": bool(s.applied),
        "created_at": s.created_at,
    }


def history_entry_to_dict(e) -> dict[str, Any]:
    return {
        "id": e.id,
        "session_id": e.session_id,
        "project_id_at_capture": e.project_id_at_capture,
        "writing_mode_at_capture": e.writing_mode_at_capture,
        "text": e.text,
        "original_text": e.original_text,
        "preview": e.preview(),
        "created_at": e.created_at,
        "updated_at": e.updated_at,
        "language": e.language,
        "source": e.source,
        "is_final": bool(e.is_final),
        "status": e.status,
        "committed_target": e.committed_target,
        "committed_at": e.committed_at,
        "duration_ms": e.duration_ms,
        "confidence": e.confidence,
        "error": e.error,
        "merged_from": list(e.merged_from),
        "split_from": e.split_from,
        "corrections": [correction_to_dict(c) for c in (e.corrections or [])],
        "sent_to_billy": bool(e.sent_to_billy),
        "billy_proposal_id": e.billy_proposal_id,
        "billy_state": e.billy_state,
        "has_audio": e.audio_bytes is not None,
        "sample_rate": e.sample_rate,
    }


def intent_to_dict(i) -> dict[str, Any]:
    return {
        "id": i.id,
        "type": i.type,
        "label": i.label,
        "enabled": bool(i.enabled),
        "requires_ai": bool(i.requires_ai),
        "requires_confirmation": bool(i.requires_confirmation),
        "reason_if_disabled": i.reason_if_disabled,
        "target_type": i.target_type,
    }


def intent_preview_to_dict(p) -> dict[str, Any]:
    return {
        "id": p.id,
        "intent_id": p.intent_id,
        "intent_type": p.intent_type,
        "project_id": p.project_id,
        "created_at": p.created_at,
        "target_summary": p.target_summary,
        "before_text": p.before_text,
        "after_text": p.after_text,
        "diff": p.diff,
        "created_note_preview": p.created_note_preview,
        "created_psyke_entry_preview": p.created_psyke_entry_preview,
        "risk_level": p.risk_level,
        "can_apply": bool(p.can_apply),
        "reason_if_blocked": p.reason_if_blocked,
        "commit_target_id": p.commit_target_id,
        "gn_field": p.gn_field,
        "gn_ref": _ref(p.gn_ref),
        "source_segment_ids": list(p.source_segment_ids),
    }


def billy_proposal_to_dict(p) -> dict[str, Any]:
    return {
        "id": p.id,
        "proposal_type": p.proposal_type,
        "operation": p.operation,
        "project_id": p.project_id,
        "created_at": p.created_at,
        "source_segment_ids": list(p.source_segment_ids),
        "prompt_text": p.prompt_text,
        "response_text": p.response_text,
        "target_summary": p.target_summary,
        "before_text": p.before_text,
        "after_text": p.after_text,
        "diff": p.diff,
        "note_preview": p.note_preview,
        "psyke_preview": p.psyke_preview,
        "gn_ref": _ref(p.gn_ref),
        "gn_field": p.gn_field,
        "can_apply": bool(p.can_apply),
        "reason_if_blocked": p.reason_if_blocked,
        "applied": bool(p.applied),
        "cancelled": bool(p.cancelled),
        "applied_at": p.applied_at,
    }


def commit_target_to_dict(t) -> dict[str, Any]:
    return {
        "id": t.id,
        "label": t.label,
        "mode": t.mode,
        "enabled": bool(t.enabled),
        "target_type": t.target_type,
        "reason_if_disabled": t.reason_if_disabled,
    }


def billy_operation_to_dict(op) -> dict[str, Any]:
    """A ``(id, label, enabled, reason)`` operation tuple -> dict."""
    return {
        "id": op[0],
        "label": op[1],
        "enabled": bool(op[2]),
        "reason_if_disabled": op[3],
    }


def backend_profile_to_dict(p) -> dict[str, Any]:
    return {
        "backend_id": p.backend_id,
        "label": p.label,
        "enabled": bool(p.enabled),
        "status": p.status,
        "ready": p.ready,
        "message": p.message,
        "model_path": p.model_path,
        "executable_path": p.executable_path,
        "language": p.language,
        "device": p.device,
        "compute_type": p.compute_type,
        "sample_rate": p.sample_rate,
        "beam_size": p.beam_size,
        "performance_profile": p.performance_profile,
        "notes": list(p.notes),
    }
