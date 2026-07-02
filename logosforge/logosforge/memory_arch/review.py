"""Memory candidate review service (Phase 4 — human-in-the-loop, non-destructive).

Implements the review half of the candidate workflow: a human (via UI or tool)
inspects proposed/speculative candidates and explicitly decides their fate.
Nothing here makes memory active automatically, and **nothing is ever deleted**
— rejection and contradiction are auditable status transitions that preserve
the object and its history.

Transitions (all require an explicit reason except plain listing/getting):
- ``approve``           → ``active``        (promotes; contradiction-surfaced)
- ``reject``            → ``rejected``      (kept for audit, not deleted)
- ``edit``              → revised content/tags (status unchanged)
- ``supersede``         → old ``superseded`` by new (old preserved + linked)
- ``mark_speculative``  → ``speculative``
- ``mark_contradicted`` → ``contradicted`` (optionally links contradicted_by)
"""

from __future__ import annotations

from logosforge.memory_arch.contradictions import ContradictionChecker
from logosforge.memory_arch.policy import MemoryWriterPolicy
from logosforge.memory_arch.schema import (
    MemoryObject,
    MemoryScope,
    MemoryStatus,
)
from logosforge.memory_arch.store import MemoryStore

# Candidate statuses awaiting a review decision (incl. policy-flagged items).
_REVIEWABLE = (MemoryStatus.PROPOSED, MemoryStatus.REVIEW_REQUIRED,
               MemoryStatus.SPECULATIVE)

# Fields a plain edit may touch — status transitions go through the dedicated
# methods so promotion/rejection stay explicit and auditable.
_EDITABLE_FIELDS = {"content", "tags", "entities", "confidence", "type",
                    "visibility"}


class MemoryCandidateReviewService:
    """Explicit, auditable review over any ``MemoryStore``."""

    def __init__(self, store: MemoryStore,
                 policy: MemoryWriterPolicy | None = None) -> None:
        self.store = store
        self.policy = policy or MemoryWriterPolicy()
        self._contradictions = ContradictionChecker()

    # ----------------------------------------------------------- read
    def list_candidates(self, scope: MemoryScope | None = None,
                        project_id: str | None = None,
                        status: MemoryStatus | None = None
                        ) -> list[MemoryObject]:
        """Candidates awaiting review (proposed + speculative by default), or a
        specific status if requested. Read-only."""
        if status is not None:
            return self.store.search("", scope=scope, project_id=project_id,
                                     filters={"status": status})
        out: list[MemoryObject] = []
        for st in _REVIEWABLE:
            out.extend(self.store.search("", scope=scope, project_id=project_id,
                                         filters={"status": st}))
        return out

    def get(self, memory_id: str) -> MemoryObject | None:
        return self.store.get(memory_id)

    # ----------------------------------------------------------- decisions
    def approve(self, memory_id: str) -> MemoryObject:
        """Promote a candidate to ``active``. Contradictions are surfaced via
        :meth:`contradictions_for` before approval — they do not block, but the
        caller is expected to have reviewed them."""
        return self.store.approve_candidate(memory_id)

    def reject(self, memory_id: str, reason: str) -> MemoryObject:
        """Decline a candidate. Non-destructive: status → ``rejected``, the
        object is kept for audit. A reason is required."""
        if not (reason or "").strip():
            raise ValueError("reject requires a non-empty reason.")
        return self.store.update(memory_id, {"status": MemoryStatus.REJECTED},
                                 reason=reason)

    def edit(self, memory_id: str, patch: dict, reason: str) -> MemoryObject:
        """Revise candidate fields (content/tags/etc.) with an audit reason.
        Refuses to change ``status`` here — use approve/reject/mark_* so status
        transitions stay explicit."""
        patch = dict(patch or {})
        if "status" in patch:
            raise ValueError(
                "edit must not change status; use approve/reject/mark_*.")
        bad = set(patch) - _EDITABLE_FIELDS
        if bad:
            raise ValueError(f"edit cannot modify fields: {sorted(bad)}")
        return self.store.update(memory_id, patch, reason=reason)

    def supersede(self, old_id: str, new_id: str,
                  reason: str) -> tuple[MemoryObject, MemoryObject]:
        """Mark ``old_id`` superseded by ``new_id`` (old preserved + linked)."""
        return self.store.supersede(old_id, new_id, reason)

    def mark_speculative(self, memory_id: str, reason: str) -> MemoryObject:
        if not (reason or "").strip():
            raise ValueError("mark_speculative requires a non-empty reason.")
        return self.store.update(memory_id,
                                 {"status": MemoryStatus.SPECULATIVE},
                                 reason=reason)

    def mark_contradicted(self, memory_id: str, reason: str,
                          contradicted_by: list[str] | None = None
                          ) -> MemoryObject:
        if not (reason or "").strip():
            raise ValueError("mark_contradicted requires a non-empty reason.")
        patch: dict = {"status": MemoryStatus.CONTRADICTED}
        if contradicted_by:
            patch["contradicted_by"] = list(contradicted_by)
        return self.store.update(memory_id, patch, reason=reason)

    # ----------------------------------------------------------- helpers
    def contradictions_for(self, memory_id: str) -> list[MemoryObject]:
        """Active/proposed memories that likely conflict with this one. Read-only;
        surfaces conflicts for the reviewer — never mutates or supersedes."""
        target = self.store.get(memory_id)
        if target is None:
            return []
        pool = [m for m in self.store.search(
                    "", scope=target.scope, project_id=target.project_id)
                if m.id != target.id
                and m.status in (MemoryStatus.ACTIVE, MemoryStatus.PROPOSED,
                                 MemoryStatus.SPECULATIVE)]
        return self._contradictions.find_contradictions(target, pool)
