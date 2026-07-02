"""LogosForge-internal assistant tools (Phase 4 — candidate workflow).

The tools from `docs/architecture/ASSISTANT_TOOLS_SPEC.md`, bound to a
`MemoryStore`. These are **LogosForge internal functions, not
provider-specific tools**. Read tools never persist; write tools only ever
create proposed/speculative candidates; activation/rejection are explicit and
auditable; cloud/GitHub sync are disabled placeholders. Nothing here is wired
into the running assistant.

Phase 4 adds the candidate workflow surface: `process_event_for_memory_candidates`
(extract→classify→propose), `list_memory_candidates`, `reject_memory_candidate`,
a deterministic `summarize_session`, and a contradiction surface that returns
candidate metadata. All remain local-only with no model call.
"""

from __future__ import annotations

from logosforge.memory_arch import candidates as _candidates
from logosforge.memory_arch.contradictions import pairwise_contradictions
from logosforge.memory_arch.github_export import GitHubMemoryExportService
from logosforge.memory_arch.policy import MemoryWriterPolicy, PolicyDecision
from logosforge.memory_arch.review import MemoryCandidateReviewService
from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from logosforge.memory_arch.store import InMemoryMemoryStore, MemoryStore
from logosforge.memory_arch.sync import MemorySyncService

_LIVE_STATUSES = (MemoryStatus.ACTIVE, MemoryStatus.PROPOSED,
                  MemoryStatus.REVIEW_REQUIRED, MemoryStatus.SPECULATIVE)


class AssistantTools:
    """Tool surface over a single memory store. Defaults to an in-memory
    store so the tools are importable/testable without any backend."""

    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or InMemoryMemoryStore()
        self.policy = MemoryWriterPolicy()
        self.review = MemoryCandidateReviewService(self.store, self.policy)
        self._sync = MemorySyncService()
        self._github = GitHubMemoryExportService(self.store)

    # -- event log (raw history layer; NOT durable memory) --------------
    def log_event(self, event_type: str, content: str,
                  project_id: str | None = None, user_id: str | None = None,
                  workspace_id: str | None = None,
                  session_id: str | None = None,
                  source: str = "", metadata: dict | None = None
                  ) -> EventLogEntry:
        """Append to the raw event log. Events are *history*, not durable
        memory — curated candidates are extracted from them, never auto-promoted."""
        return self.store.add_event(EventLogEntry(
            event_type=event_type, content=content, project_id=project_id,
            user_id=user_id, workspace_id=workspace_id, session_id=session_id,
            source=source, metadata=metadata or {}))

    # -- read tools (never persist) -------------------------------------
    def search_memory(self, query: str, scope=None, project_id=None,
                      filters=None) -> list[MemoryObject]:
        return self.store.search(query, scope=scope, project_id=project_id,
                                 filters=filters)

    def retrieve_project_state(self, project_id: str,
                               include_proposed: bool = False) -> dict:
        items = [m for m in self.store.search("", scope=MemoryScope.PROJECT,
                                              project_id=project_id)
                 if self._live(m, include_proposed)]
        return {"project_id": project_id, "memory": items, "structure": []}

    def retrieve_user_preferences(self, task_type: str | None = None,
                                  include_proposed: bool = False
                                  ) -> list[MemoryObject]:
        return self._active_by_types(
            MemoryScope.USER,
            {MemoryType.PREFERENCE, MemoryType.MODEL_PREFERENCE,
             MemoryType.WORKFLOW_RULE, MemoryType.PROCEDURAL_RULE},
            include_proposed)

    def retrieve_assistant_rules(self, context=None,
                                 include_proposed: bool = False
                                 ) -> list[MemoryObject]:
        return self._active_by_types(
            MemoryScope.ASSISTANT,
            {MemoryType.ASSISTANT_RULE, MemoryType.PROCEDURAL_RULE,
             MemoryType.WORKFLOW_RULE},
            include_proposed)

    def _active_by_types(self, scope: MemoryScope, types: set,
                         include_proposed: bool = False) -> list[MemoryObject]:
        return [m for m in self.store.search("", scope=scope)
                if m.type in types and self._live(m, include_proposed)]

    @staticmethod
    def _live(mem: MemoryObject, include_proposed: bool) -> bool:
        if mem.status is MemoryStatus.ACTIVE:
            return True
        return include_proposed and mem.status in (MemoryStatus.PROPOSED,
                                                   MemoryStatus.SPECULATIVE)

    def list_memory_candidates(self, scope=None, project_id=None, status=None
                               ) -> list[MemoryObject]:
        """Candidates awaiting review (proposed + speculative by default)."""
        return self.review.list_candidates(scope=scope, project_id=project_id,
                                           status=status)

    # -- write tools (candidates only; explicit approval) ---------------
    def write_memory_candidate(self, content: str, type: MemoryType,
                               scope: MemoryScope, confidence: float = 0.0,
                               source: str | None = None,
                               project_id: str | None = None,
                               user_id: str | None = None) -> MemoryObject:
        """Propose a memory, routed through the writer policy. Safe,
        high-confidence, durable memory may **auto-save as active**; uncertain/
        sensitive/conflicting memory becomes proposed/review_required/speculative;
        secrets/raw-audio are rejected. Never stores secrets or raw audio."""
        forbidden = self.policy.check_forbidden_content_text(content)
        if forbidden:
            raise ValueError(f"refused forbidden content: {forbidden}")
        mem = MemoryObject(
            scope=scope, type=type, content=content, confidence=confidence,
            source_event=source, project_id=project_id, user_id=user_id,
            status=MemoryStatus.PROPOSED)
        self.policy.validate_scope(mem)
        existing = self.store.search("", scope=scope, project_id=project_id)
        result = self.policy.evaluate(mem, existing=existing)
        mem.policy_decision = result.decision.value
        mem.risk_level = result.risk_level
        if result.sensitive_flags:
            mem.sensitive_flags = list(result.sensitive_flags)
        if result.decision is PolicyDecision.REJECT:
            raise ValueError(f"refused forbidden content: {result.reason}")
        if result.decision is PolicyDecision.AUTO_SAVE_ACTIVE:
            mem.status = MemoryStatus.ACTIVE
            mem.auto_saved = True
            return self.store.save_active(mem)
        if result.decision is PolicyDecision.SAVE_SPECULATIVE:
            mem.status = MemoryStatus.SPECULATIVE
            return self.store.write_candidate(mem)
        if result.requires_review:
            mem.status = MemoryStatus.REVIEW_REQUIRED
            mem.requires_review = True
            mem.review_reason = result.reason
            if result.contradiction_ids:
                mem.contradicted_by = list(result.contradiction_ids)
            return self.store.write_candidate(mem)
        mem.status = MemoryStatus.PROPOSED          # save_proposed / explicit ignore
        return self.store.write_candidate(mem)

    def process_event_for_memory_candidates(self, event: EventLogEntry,
                                            context: dict | None = None
                                            ) -> _candidates.PipelineResult:
        """Extract → classify → propose candidates from one event. Writes only
        proposed/speculative objects; returns written/skipped/warnings."""
        return _candidates.process_event_for_memory_candidates(
            self.store, event, context=context, policy=self.policy)

    def summarize_session(self, session_id: str) -> dict:
        """Deterministic, local-only session summary (no model call). Writes a
        single **proposed** session-summary candidate at assistant scope."""
        return _candidates.summarize_session(self.store, session_id,
                                             policy=self.policy)

    def capture_interaction(self, user_message: str = "",
                            assistant_response: str = "", *,
                            source: str = "assistant_panel", **context) -> dict:
        """Controlled passive runtime capture of a completed exchange. No-op
        unless ``assistant_auto_memory_enabled`` is on; runs the policy pipeline
        over a sanitized event (safe memory auto-saves, risky goes to review);
        never calls a provider/cloud/GitHub; never stores secrets/raw audio."""
        from logosforge.assistant_arch import auto_memory
        return auto_memory.capture_interaction(
            user_message=user_message, assistant_response=assistant_response,
            source=source, store=self.store, policy=self.policy, **context)

    def approve_memory_candidate(self, memory_id: str) -> MemoryObject:
        return self.review.approve(memory_id)

    def reject_memory_candidate(self, memory_id: str, reason: str
                                ) -> MemoryObject:
        """Decline a candidate (status → rejected; preserved for audit)."""
        return self.review.reject(memory_id, reason)

    def update_memory(self, memory_id: str, patch: dict,
                      reason: str) -> MemoryObject:
        return self.store.update(memory_id, patch, reason)

    def supersede_memory(self, old_id: str, new_id: str, reason: str):
        return self.review.supersede(old_id, new_id, reason)

    def find_contradictions(self, topic: str, project_id=None) -> list[dict]:
        """Surface conflicting memory on a topic with candidate metadata.

        Returns dicts ``{"kind", "reason", "memories": [...]}`` combining rows
        already flagged ``contradicted`` with heuristic pairs among live
        (active/proposed/speculative) memory. Read-only — never mutates."""
        results: list[dict] = []
        for m in self.store.find_contradictions(topic, project_id=project_id):
            results.append({"kind": "flagged",
                            "reason": "already marked contradicted",
                            "memories": [m]})
        pool = [m for m in self.store.search(topic, project_id=project_id)
                if m.status in _LIVE_STATUSES]
        for a, b, reason in pairwise_contradictions(pool):
            results.append({"kind": "heuristic", "reason": reason,
                            "memories": [a, b]})
        return results

    def export_memory_to_markdown(self, scope=None, project_id=None) -> str:
        return self.store.export_markdown(scope=scope, project_id=project_id)

    # -- sync / github (disabled placeholders) --------------------------
    def sync_memory_to_cloud(self) -> dict:
        return self._sync.sync_memory_to_cloud()

    def optional_sync_memory_to_github(self) -> dict:
        return self._github.optional_sync_memory_to_github()
