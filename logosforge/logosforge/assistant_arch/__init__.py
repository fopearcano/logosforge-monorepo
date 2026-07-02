"""LogosForge assistant orchestration — Phase 2 interfaces/stubs (isolated).

Model gateway, context builder, candidate extractor, orchestration skeleton,
and the internal assistant tool surface. **Stubs only** — no external
provider calls, no model behavior change, no UI wiring, no automatic durable
memory writes. The existing Alpha assistant (`logosforge/assistant.py`,
Billy/Logos/Dexter) is untouched.

Naming: the architecture docs call the unified assistant "Jordan"
(`docs/architecture/JORDAN_EXTERNALIZED_SELF_MODEL.md`); the live surfaces
remain Billy/Logos/Dexter. No code is renamed here.
"""

from __future__ import annotations

from logosforge.assistant_arch.context_builder import (
    AssistantContextBuilder,
    ContextBundle,
    MemoryCandidateExtractor,
)
from logosforge.assistant_arch.model_gateway import (
    DummyModelProvider,
    ModelGateway,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapability,
    ProviderType,
)
from logosforge.assistant_arch.orchestration import (
    AssistantOrchestrator,
    OrchestrationResult,
)
from logosforge.assistant_arch.tools import AssistantTools

__all__ = [
    "AssistantContextBuilder",
    "ContextBundle",
    "MemoryCandidateExtractor",
    "ModelGateway",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "ProviderCapability",
    "ProviderType",
    "DummyModelProvider",
    "AssistantOrchestrator",
    "OrchestrationResult",
    "AssistantTools",
]
