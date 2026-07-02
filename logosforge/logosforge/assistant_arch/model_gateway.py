"""Model gateway abstraction (Phase 2 stub).

Mirrors `docs/architecture/MODEL_GATEWAY_SPEC.md`. The Alpha already seeds
provider capabilities in ``logosforge/providers.py``; this is the
forward-looking abstraction. **No provider is called here** — the only
concrete provider is a deterministic dummy for tests. Providers generate;
they never own memory.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum


class ProviderType(str, Enum):
    LOCAL = "local"
    SELF_HOSTED = "self_hosted"
    CLOUD = "cloud"


@dataclass
class ProviderCapability:
    provider_id: str
    provider_type: ProviderType
    base_url: str = ""
    auth_mode: str = "none"            # none | api_key | custom_header
    models: list[str] = field(default_factory=list)
    context_window: int = 0
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_json_schema: bool = False
    supports_embeddings: bool = False
    supports_vision: bool = False
    supports_audio: bool = False
    privacy_mode: str = "local_only"   # local_only | cloud
    latency_class: str = "unknown"
    cost_class: str = "unknown"
    offline_capable: bool = False


@dataclass
class ModelRequest:
    provider_id: str
    model: str
    messages: list[dict]
    system_context: str = ""
    tools: list[dict] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 0
    stream: bool = False
    response_format: dict | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ModelResponse:
    provider_id: str
    model: str
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    raw_response: object | None = None
    metadata: dict = field(default_factory=dict)


class ModelProvider(abc.ABC):
    @abc.abstractmethod
    def get_capabilities(self) -> ProviderCapability: ...

    @abc.abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse: ...

    def stream(self, request: ModelRequest):
        # Default: yield the single non-streaming response. Real streaming
        # providers override. Never calls an external service in Phase 2.
        yield self.generate(request)

    def validate_request(self, request: ModelRequest) -> None:
        if not request.provider_id:
            raise ValueError("ModelRequest.provider_id is required.")
        if not request.messages:
            raise ValueError("ModelRequest.messages must be non-empty.")


class DummyModelProvider(ModelProvider):
    """Deterministic, offline test provider. Calls nothing; stores nothing."""

    def __init__(self, provider_id: str = "dummy",
                 provider_type: ProviderType = ProviderType.LOCAL) -> None:
        self._id = provider_id
        self._type = provider_type

    def get_capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=self._id, provider_type=self._type,
            models=["dummy-1"], context_window=8192,
            supports_streaming=True, supports_tools=False,
            privacy_mode="local_only"
            if self._type is not ProviderType.CLOUD else "cloud",
            offline_capable=self._type is not ProviderType.CLOUD)

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.validate_request(request)
        last = request.messages[-1].get("content", "") if request.messages else ""
        return ModelResponse(
            provider_id=self._id, model=request.model or "dummy-1",
            content=f"[dummy:{self._id}] {last}",
            usage={"prompt_tokens": 0, "completion_tokens": 0})


class ModelGateway:
    """Registry + router over providers. Holds capabilities, not memory."""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register_provider(self, provider: ModelProvider) -> None:
        cap = provider.get_capabilities()
        self._providers[cap.provider_id] = provider

    def list_providers(self) -> list[ProviderCapability]:
        return [p.get_capabilities() for p in self._providers.values()]

    def select_provider(self, task_context=None) -> str:
        # Stub: first registered provider. Real selection (capability match,
        # privacy, cost/latency) is a later phase.
        if not self._providers:
            raise ValueError("no providers registered.")
        return next(iter(self._providers))

    def generate(self, request: ModelRequest) -> ModelResponse:
        provider = self._providers.get(request.provider_id)
        if provider is None:
            raise ValueError(f"provider not registered: {request.provider_id}")
        return provider.generate(request)
