"""Controlled passive runtime capture for the automatic memory pipeline.

Bridges a *completed* assistant exchange into the policy-governed memory pipeline
— **opt-in, default-off, local-only, fail-safe, read/write of memory only**:

- Gated by `assistant_auto_memory_enabled` (settings, default off). Disabled →
  a pure no-op; runtime behavior is exactly as before.
- Runs **after** response generation; never before, never blocking the reply.
- Builds a **sanitized** event (secrets / raw-audio / raw-audio paths redacted),
  logs it, and runs `process_event_for_memory_candidates` so the writer policy
  decides: safe high-confidence durable memory auto-saves active; uncertain /
  sensitive / contradictory / scope-ambiguous memory is flagged for review.
- **Never** calls a provider, cloud sync, or GitHub; never stores raw audio,
  raw transcripts wholesale, secrets, or provider keys; never crashes the
  assistant (any failure degrades to a safe status).

Production note: a concrete store is **not** wired here. Enabling the flag alone
changes nothing until a store is registered (`passive_context.register_memory_store`)
or passed per call — keeping Alpha behavior unchanged while the seam is in place.
"""

from __future__ import annotations

import re

_AUTO_KEY = "assistant_auto_memory_enabled"
_DIAG_KEY = "assistant_auto_memory_diagnostics_enabled"

_MAX_EXCERPT = 1000              # cap stored exchange excerpt (no full transcript)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")

# Sources allowed at safe assistant-session boundaries.
SOURCES = ("billy", "logos", "dexter_text", "assistant_panel", "other")


def is_auto_memory_enabled() -> bool:
    try:
        from logosforge.settings import get_manager
        return bool(get_manager().get(_AUTO_KEY))
    except Exception:
        return False


def is_auto_memory_diagnostics_enabled() -> bool:
    try:
        from logosforge.settings import get_manager
        return bool(get_manager().get(_DIAG_KEY))
    except Exception:
        return False


def _sanitize(text: str, policy) -> str:
    """Redact secret / raw-audio / debug sentences; cap length. The event log
    must never hold a secret even though the writer policy also rejects it."""
    if not text:
        return ""
    parts = []
    for seg in _SENTENCE.split(text):
        seg = seg.strip()
        if not seg:
            continue
        parts.append("[redacted]" if policy.check_forbidden_content_text(seg)
                     else seg)
    return " ".join(parts)[:_MAX_EXCERPT]


def _summary(result, policy, event_id: str) -> dict:
    from logosforge.memory_arch.schema import MemoryStatus
    written = result.written
    skipped = result.skipped

    def count(status):
        return sum(1 for m in written if m.status is status)

    ignored = sum(1 for s in skipped if "ignored" in (s.get("reason") or ""))
    rejected = sum(1 for s in skipped
                   if "rejected" in (s.get("reason") or "")
                   or "forbidden" in (s.get("reason") or ""))
    contradiction = sum(1 for w in result.warnings if "contradiction" in w)
    # Warnings are id/reason-level; redact defensively (never echo content).
    warnings = ["[redacted]" if policy.check_forbidden_content_text(w) else w
                for w in result.warnings]
    return {
        "status": "ok", "event_id": event_id, "events_processed": 1,
        "candidates_extracted": len(written) + len(skipped),
        "auto_saved_count": count(MemoryStatus.ACTIVE),
        "review_required_count": count(MemoryStatus.REVIEW_REQUIRED),
        "proposed_count": count(MemoryStatus.PROPOSED),
        "speculative_count": count(MemoryStatus.SPECULATIVE),
        "ignored_count": ignored, "rejected_count": rejected,
        "contradiction_count": contradiction, "warnings": warnings,
    }


def capture_interaction(*, user_message: str = "", assistant_response: str = "",
                        source: str = "assistant_panel",
                        project_id=None, user_id=None, workspace_id=None,
                        session_id=None, current_mode=None, active_section=None,
                        active_entities=None, provider_id=None, model=None,
                        store=None, policy=None) -> dict:
    """Process a completed exchange through the automatic memory pipeline.

    Returns a safe status/summary dict (counts only when diagnostics are on).
    No-op (``{"status": "disabled"}``) unless the flag is on. Never raises,
    never calls a provider/cloud/GitHub, never stores secrets or raw audio.
    """
    if not is_auto_memory_enabled():
        return {"status": "disabled"}
    diag = is_auto_memory_diagnostics_enabled()
    try:
        from logosforge.assistant_arch import passive_context
        from logosforge.memory_arch.candidates import (
            process_event_for_memory_candidates)
        from logosforge.memory_arch.policy import MemoryWriterPolicy
        from logosforge.memory_arch.schema import EventLogEntry

        policy = policy or MemoryWriterPolicy()
        store = store if store is not None else passive_context.get_memory_store()
        if store is None:
            return {"status": "no_store",
                    "warnings": ["no memory store registered; skipped."]
                    if diag else []}

        content = "\n".join(x for x in (_sanitize(user_message, policy),
                                        _sanitize(assistant_response, policy))
                            if x)
        if not content.strip():
            return {"status": "empty"}

        event = EventLogEntry(
            event_type="assistant_interaction", content=content,
            source=source if source in SOURCES else "other",
            project_id=project_id, user_id=user_id, workspace_id=workspace_id,
            session_id=session_id,
            metadata={                              # ids/mode only — never keys
                "current_mode": current_mode, "active_section": active_section,
                "selected_entities": list(active_entities or []),
                "provider_id": provider_id, "model": model})
        store.add_event(event)

        result = process_event_for_memory_candidates(
            store, event,
            context={"project_id": project_id, "user_id": user_id,
                     "workspace_id": workspace_id, "current_mode": current_mode},
            policy=policy)
        summary = _summary(result, policy, event.id)
        if diag:
            return summary
        return {"status": "ok", "event_id": event.id,
                "auto_saved_count": summary["auto_saved_count"],
                "review_required_count": summary["review_required_count"]}
    except Exception:
        return {"status": "error"}                  # fail-safe; never block reply
