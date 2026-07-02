"""Assistant orchestration skeleton (Phase 2 stub).

Mirrors `docs/architecture/ASSISTANT_ORCHESTRATION_LAYER.md`. Wires the
read-only context builder, the model gateway, the writer policy, and the
candidate extractor into one place — **without** changing the running
assistant. It performs no automatic durable writes: it only *proposes*
candidates and leaves approval explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logosforge.assistant_arch.context_builder import (
    AssistantContextBuilder,
    ContextBundle,
    MemoryCandidateExtractor,
)
from logosforge.assistant_arch.model_gateway import ModelGateway
from logosforge.memory_arch.contradictions import ContradictionChecker
from logosforge.memory_arch.policy import MemoryWriterPolicy
from logosforge.memory_arch.schema import MemoryObject
from logosforge.memory_arch.store import MemoryStore


@dataclass
class OrchestrationResult:
    context: ContextBundle
    proposed_candidates: list[MemoryObject] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class AssistantOrchestrator:
    """Composes the Phase-2 pieces. Not connected to the live UI/assistant."""

    def __init__(self, store: MemoryStore | None = None,
                 gateway: ModelGateway | None = None) -> None:
        self._store = store
        self._gateway = gateway
        self._context = AssistantContextBuilder(store, gateway)
        self._policy = MemoryWriterPolicy()
        self._extractor = MemoryCandidateExtractor()
        self._contradictions = ContradictionChecker()

    def build_context(self, user_request: str, project_id=None, user_id=None,
                      workspace_id=None, provider_id=None) -> ContextBundle:
        return self._context.build_context(
            user_request, project_id, user_id, workspace_id, provider_id)

    def propose_memory_from_session(self, session_or_event,
                                    context=None) -> list[MemoryObject]:
        """Extract candidates (placeholder → empty) and return them WITHOUT
        writing. Durable writes remain explicit (approve_candidate)."""
        candidates = self._extractor.extract_candidates(session_or_event,
                                                        context)
        # Conservative filter; nothing is persisted here.
        return [c for c in candidates
                if self._policy.should_save_candidate(c.content, context)]
