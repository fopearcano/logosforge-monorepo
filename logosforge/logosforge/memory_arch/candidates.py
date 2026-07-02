"""Memory candidate workflow (Phase 4 — extract · classify · propose).

The heart of the candidate workflow described in
`docs/architecture/ASSISTANT_MEMORY_SPEC.md` and `ASSISTANT_TOOLS_SPEC.md`.

Core principle: **the model generates; LogosForge remembers.** This module is
the "remember" side — it turns an interaction event into *candidate* memory,
**deterministically and with no model call, no network, no embeddings**:

- Only spans carrying an explicit memory **marker** become candidates — raw
  chat is never auto-saved as fact (anti-spam).
- Every candidate is written **proposed** (or **speculative**) only — nothing
  becomes active without explicit human approval.
- Project Memory and Assistant Meta-Memory stay separate by scope.
- Secrets / raw-audio / debug spans are dropped by the writer policy.
- A span that infers `project` scope without a `project_id` (or `user` scope
  without a `user_id`) is **skipped with a warning**, never mis-filed.

Nothing here is wired into the running Alpha; importing it touches no DB,
provider, or UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from logosforge.memory_arch.contradictions import contradicts
from logosforge.memory_arch.policy import MemoryWriterPolicy, PolicyDecision
from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from logosforge.memory_arch.store import MemoryStore

# Confidence tiers (per spec): low / medium / high.
_LOW, _MEDIUM, _HIGH = 0.3, 0.6, 0.9

# Bound how much a single event may produce, and how long a candidate gets —
# further anti-spam guards on top of the marker requirement.
_MAX_CANDIDATES_PER_EVENT = 20
_MAX_CONTENT_CHARS = 500


@dataclass(frozen=True)
class _Marker:
    """A trigger phrase family → memory classification."""
    label: str
    pattern: "re.Pattern[str]"
    type: MemoryType
    scope: MemoryScope            # base scope; speculative is resolved per-context
    confidence: float
    status: MemoryStatus = MemoryStatus.PROPOSED


def _rx(*phrases: str) -> "re.Pattern[str]":
    return re.compile("|".join(phrases), re.IGNORECASE)


# Ordered by priority — the FIRST marker that matches a span classifies it.
# correction → release_blocker → architecture → deferred → workflow →
# project_decision → preference → speculative.
_MARKERS: tuple[_Marker, ...] = (
    _Marker(
        "correction",
        _rx(r"\bcorrection\s*:", r"\bno,?\s+(that|this)('?s| is)\s+wrong\b",
            r"\b(that|this)('?s| is)\s+(wrong|incorrect)\b",
            r"\byou\s+were\s+wrong\b", r"\bactually,?\s+(that|this)('?s| is)\s+wrong\b"),
        MemoryType.MISTAKE_CORRECTION, MemoryScope.ASSISTANT, _HIGH),
    _Marker(
        "release_blocker",
        _rx(r"\brelease[\s\-]?block(er|ing)\b", r"\bblocks?\s+(the\s+)?release\b",
            r"\bmust\s+fix\s+before\s+release\b", r"\brelease\s+blocker\b"),
        MemoryType.RELEASE_BLOCKER_RULE, MemoryScope.ASSISTANT, _HIGH),
    _Marker(
        "architecture",
        _rx(r"\barchitecture\s+decision\b", r"\barchitecturally\b",
            r"\bdesign\s+decision\b", r"\bthe\s+architecture\s+is\b"),
        MemoryType.ARCHITECTURE_DECISION, MemoryScope.ASSISTANT, _MEDIUM),
    _Marker(
        "deferred",
        _rx(r"\bdefer(red|ring)?\b", r"\bfuture\s+scaffold\b", r"\blater\s+phase\b",
            r"\bpost[\s\-]?alpha\b", r"\bfuture\s+phase\b", r"\bnot\s+now\b"),
        MemoryType.DEFERRED_FEATURE, MemoryScope.ASSISTANT, _MEDIUM),
    _Marker(
        "workflow",
        _rx(r"\bthe\s+workflow\b", r"\bworkflow\s+rule\b", r"\bthe\s+procedure\b",
            r"\bmake\s+it\s+a\s+rule\b", r"\bas\s+a\s+rule\b", r"\bthe\s+process\s+is\b"),
        MemoryType.WORKFLOW_RULE, MemoryScope.ASSISTANT, _MEDIUM),
    _Marker(
        "project_decision",
        _rx(r"\bfor\s+this\s+project\b", r"\bwe\s+decided\b", r"\bcanonically\b",
            r"\bin\s+this\s+story\b", r"\bthe\s+canon\s+is\b", r"\bin\s+this\s+world\b"),
        MemoryType.PROJECT_DECISION, MemoryScope.PROJECT, _MEDIUM),
    _Marker(
        "preference",
        _rx(r"\bi\s+prefer\b", r"\bi'?d\s+prefer\b", r"\bfrom\s+now\s+on\b",
            r"\balways\b", r"\bnever\b", r"\bi\s+like\b", r"\bmy\s+preference\b"),
        MemoryType.PREFERENCE, MemoryScope.USER, _MEDIUM),
    _Marker(
        "speculative",
        _rx(r"\bmaybe\b", r"\bwhat\s+if\b", r"\bidea\s*:", r"\bpossibly\b",
            r"\bcould\s+we\b", r"\bi\s+wonder\b", r"\bbrainstorm\b",
            r"\bspeculativ", r"\bperhaps\b"),
        MemoryType.SPECULATIVE_IDEA, MemoryScope.PROJECT, _LOW,
        MemoryStatus.SPECULATIVE),
)


@dataclass
class CandidateClassification:
    """The deterministic verdict for one marked span."""
    type: MemoryType
    scope: MemoryScope
    confidence: float
    status: MemoryStatus
    marker: str


@dataclass
class ExtractionResult:
    """Outcome of turning text/an event into candidates (nothing written yet)."""
    candidates: list[MemoryObject] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Outcome of the full event → proposed-candidate pipeline."""
    event_id: str | None = None
    written: list[MemoryObject] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def written_ids(self) -> list[str]:
        return [m.id for m in self.written]


def classify_span(text: str, *, project_id: str | None = None
                  ) -> CandidateClassification | None:
    """Classify a single span by the first matching marker (priority order).
    Returns ``None`` for unmarked text — unmarked chat never becomes memory."""
    for marker in _MARKERS:
        if marker.pattern.search(text):
            scope = marker.scope
            # Speculative ideas attach to the project when known, else stay
            # assistant-meta speculation (so they are never silently dropped).
            if marker.label == "speculative":
                scope = (MemoryScope.PROJECT if project_id
                         else MemoryScope.ASSISTANT)
            return CandidateClassification(
                type=marker.type, scope=scope, confidence=marker.confidence,
                status=marker.status, marker=marker.label)
    return None


def _split_segments(text: str) -> list[str]:
    """Sentence/line segmentation — coarse but deterministic and dependency-free."""
    rough = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [s.strip() for s in rough if s and s.strip()]


def extract_candidates(text: str, *, policy: MemoryWriterPolicy | None = None,
                       project_id: str | None = None,
                       user_id: str | None = None,
                       workspace_id: str | None = None,
                       source_event: str | None = None) -> ExtractionResult:
    """Heuristically extract proposed/speculative candidates from text.

    Builds (does not persist) ``MemoryObject``s. Drops forbidden spans and
    skips spans whose inferred scope lacks a required id — each with a reason.
    """
    policy = policy or MemoryWriterPolicy()
    result = ExtractionResult()
    seen: set[tuple[str, str, str]] = set()

    for segment in _split_segments(text):
        if len(result.candidates) >= _MAX_CANDIDATES_PER_EVENT:
            result.warnings.append(
                "candidate cap reached for this event; remaining spans ignored.")
            break
        verdict = classify_span(segment, project_id=project_id)
        if verdict is None:
            continue                                  # unmarked → not memory
        content = segment[:_MAX_CONTENT_CHARS].strip()
        if not content:
            continue

        # Drop obvious secrets / raw-audio / debug before anything else.
        forbidden = policy.check_forbidden_content_text(content)
        if forbidden:
            result.skipped.append({"content": content,
                                   "reason": f"forbidden content: {forbidden}"})
            continue

        # Scope/id integrity — never mis-file Project vs User memory.
        if verdict.scope is MemoryScope.PROJECT and not project_id:
            result.skipped.append({
                "content": content,
                "reason": "project-scope marker but no project_id in context."})
            result.warnings.append(
                f"skipped project candidate (no project_id): {content[:60]!r}")
            continue
        if verdict.scope is MemoryScope.USER and not user_id:
            result.skipped.append({
                "content": content,
                "reason": "user-scope marker but no user_id in context."})
            result.warnings.append(
                f"skipped user candidate (no user_id): {content[:60]!r}")
            continue

        key = (content.lower(), verdict.type.value, verdict.scope.value)
        if key in seen:
            continue
        seen.add(key)

        try:
            mem = MemoryObject(
                scope=verdict.scope, type=verdict.type, content=content,
                confidence=verdict.confidence, status=verdict.status,
                source_event=source_event,
                project_id=project_id if verdict.scope is MemoryScope.PROJECT else None,
                user_id=user_id if verdict.scope is MemoryScope.USER else None,
                workspace_id=workspace_id,
                tags=[verdict.marker])
        except ValueError as exc:                     # schema invariant guard
            result.skipped.append({"content": content, "reason": str(exc)})
            continue

        # Final defensive scope check (Project↔Assistant separation).
        try:
            policy.validate_scope(mem)
        except ValueError as exc:
            result.skipped.append({"content": content, "reason": str(exc)})
            continue

        result.candidates.append(mem)

    return result


def process_event_for_memory_candidates(
        store: MemoryStore, event: EventLogEntry,
        context: dict | None = None,
        policy: MemoryWriterPolicy | None = None) -> PipelineResult:
    """Full pipeline: validate → policy → extract → classify → forbidden-check
    → scope-check → contradiction-check → write **proposed/speculative only**.

    Returns the written candidates, skipped spans (with reasons), and warnings.
    Does **not** auto-log the event and does **not** make any memory active.
    """
    policy = policy or MemoryWriterPolicy()
    context = context or {}
    out = PipelineResult(event_id=getattr(event, "id", None))

    content = getattr(event, "content", "") or ""
    if not content.strip():
        out.warnings.append("event has no content; nothing to extract.")
        return out

    # Context ids: explicit overrides win, else fall back to the event's own.
    project_id = context.get("project_id", getattr(event, "project_id", None))
    user_id = context.get("user_id", getattr(event, "user_id", None))
    workspace_id = context.get("workspace_id",
                               getattr(event, "workspace_id", None))

    extracted = extract_candidates(
        content, policy=policy, project_id=project_id, user_id=user_id,
        workspace_id=workspace_id, source_event=getattr(event, "id", None))
    out.skipped.extend(extracted.skipped)
    out.warnings.extend(extracted.warnings)

    for cand in extracted.candidates:
        # Same-scope memory: used for the (non-blocking) contradiction warning
        # and for the policy decision (duplicate / contradiction gating).
        try:
            existing = store.search("", scope=cand.scope,
                                    project_id=cand.project_id)
        except Exception:
            existing = []
        for other in existing:
            reason = contradicts(cand, other)
            if reason:
                out.warnings.append(
                    f"possible contradiction with {other.id}: {reason}")

        # Automatic, policy-governed decision: auto-save safe memory as active;
        # flag uncertain/sensitive/conflicting/scope-ambiguous for review.
        result = policy.evaluate(cand, existing=existing, context=context)
        cand.policy_decision = result.decision.value
        cand.risk_level = result.risk_level
        if result.sensitive_flags:
            cand.sensitive_flags = list(result.sensitive_flags)

        if result.decision is PolicyDecision.REJECT:
            out.skipped.append({"content": cand.content,
                                "reason": f"policy: rejected ({result.reason})"})
            continue
        if result.decision is PolicyDecision.IGNORE:
            out.skipped.append({"content": cand.content,
                                "reason": f"policy: ignored ({result.reason})"})
            continue

        try:
            if result.decision is PolicyDecision.AUTO_SAVE_ACTIVE:
                cand.status = MemoryStatus.ACTIVE
                cand.auto_saved = True
                out.written.append(store.save_active(cand))
            elif result.decision is PolicyDecision.SAVE_SPECULATIVE:
                cand.status = MemoryStatus.SPECULATIVE
                out.written.append(store.write_candidate(cand))
            elif result.requires_review:
                cand.status = MemoryStatus.REVIEW_REQUIRED
                cand.requires_review = True
                cand.review_reason = result.reason
                if result.contradiction_ids:
                    cand.contradicted_by = list(result.contradiction_ids)
                out.written.append(store.write_candidate(cand))
            else:                                     # SAVE_PROPOSED
                cand.status = MemoryStatus.PROPOSED
                out.written.append(store.write_candidate(cand))
        except ValueError as exc:                     # policy/store refusal
            out.skipped.append({"content": cand.content, "reason": str(exc)})

    return out


def _redact(text: str, policy: MemoryWriterPolicy) -> str:
    """Replace a forbidden excerpt wholesale so summaries never leak secrets."""
    return "[redacted]" if policy.check_forbidden_content_text(text) else text


def summarize_session(store: MemoryStore, session_id: str,
                      policy: MemoryWriterPolicy | None = None) -> dict:
    """Deterministic, local-only session summary (no model call).

    Reads the event log for ``session_id``, builds a compact summary string
    (event counts + redacted excerpts), and writes **one proposed**
    ``session_summary`` candidate at **assistant** scope (it is meta-memory
    about the work session, kept apart from Project Memory). Returns a status
    dict; writes nothing when the session has no events.
    """
    policy = policy or MemoryWriterPolicy()
    events = store.list_events(session_id=session_id)
    if not events:
        return {"status": "empty", "session_id": session_id,
                "summary": "", "candidate_id": None}

    by_type: dict[str, int] = {}
    for ev in events:
        by_type[ev.event_type] = by_type.get(ev.event_type, 0) + 1
    counts = ", ".join(f"{k}×{v}" for k, v in sorted(by_type.items()))

    excerpts = []
    for ev in events[:5]:
        snippet = _redact((ev.content or "").strip()[:80], policy)
        if snippet:
            excerpts.append(f"{ev.event_type}: {snippet}")

    summary = (f"Session {session_id}: {len(events)} events ({counts}). "
               + (" | ".join(excerpts) if excerpts else ""))
    summary = summary.strip()[:_MAX_CONTENT_CHARS]

    cand = MemoryObject(
        scope=MemoryScope.ASSISTANT, type=MemoryType.SESSION_SUMMARY,
        content=summary, confidence=_MEDIUM, status=MemoryStatus.PROPOSED,
        tags=["session_summary"], entities=[session_id])
    written = store.write_candidate(cand)
    return {"status": "proposed", "session_id": session_id,
            "summary": summary, "candidate_id": written.id,
            "event_count": len(events)}
