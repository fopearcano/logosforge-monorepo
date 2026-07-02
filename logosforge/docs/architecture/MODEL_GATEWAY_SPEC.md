# Model Gateway Spec

> Phase 1 — provider-abstraction **direction**. The Alpha already seeds this
> in `logosforge/providers.py` (`ProviderCapabilities`,
> `PROVIDER_CAPABILITIES`, `build_active_provider`) and `assistant.py`
> (`chat_completion` with OpenAI/Anthropic API formats). This document
> describes where that abstraction goes; it implements nothing new.

## Principle

**Model providers generate / reason. They do not own LogosForge memory.**
The gateway is a thin, swappable adapter layer between the Assistant Engine
and any backend. Swapping providers must never lose memory.

## Supported providers

LM Studio · Ollama · vLLM · OpenAI · Anthropic · OpenRouter · future
providers. *(vLLM is not yet in the Alpha's `PROVIDER_CAPABILITIES`; it is a
planned addition — see contradictions in the after-work report.)*

## Gateway responsibilities

1. Normalize provider **requests**.
2. Normalize provider **responses**.
3. Handle **streaming**.
4. Handle **tool-call** compatibility.
5. Handle **structured output** (JSON schema) compatibility.
6. Handle **context-window / capability** metadata.
7. Handle **local vs cloud privacy** differences.
8. **Report provider capabilities** to the Assistant Engine.
9. **Never become the memory store.**

## Provider capability descriptor

(Generalizes today's `ProviderCapabilities`.)

| Field | Meaning |
|-------|---------|
| `provider_id` | Stable id (e.g. `lm_studio`, `ollama`, `vllm`, `openai`, `anthropic`, `openrouter`). |
| `provider_type` | `local` · `self_hosted` · `cloud`. |
| `base_url` | Endpoint. |
| `auth_mode` | `none` · `api_key` · `custom_header`. |
| `models` | Available/known models. |
| `context_window` | Max tokens. |
| `supports_streaming` | bool. |
| `supports_tools` | bool. |
| `supports_json_schema` | bool. |
| `supports_embeddings` | bool. |
| `supports_vision` | bool. |
| `supports_audio` | bool. |
| `privacy_mode` | e.g. `local_only` · `cloud`. |
| `latency_class` | rough latency tier. |
| `cost_class` | rough cost tier. |
| `offline_capable` | bool. |

## Provider notes (memory always belongs to LogosForge)

- **LM Studio** — local/self-hosted; exposes a local OpenAI-compatible API
  (Alpha default `http://localhost:1234/v1`, no key). Memory → LogosForge.
- **Ollama** — local/self-hosted; local API (`:11434/v1`). Memory → LogosForge.
- **vLLM** — self-hosted inference server. Memory → LogosForge.
- **OpenAI** — cloud. Memory → LogosForge.
- **Anthropic** — cloud (distinct API format; already handled in
  `assistant.py`). Memory → LogosForge.
- **OpenRouter** — cloud routing/marketplace. Memory → LogosForge.

## Boundary

The gateway returns generated text/structured output + capability metadata
to the Assistant Engine. It must not read, write, retrieve, or persist
memory objects. All memory operations go through the assistant tools
(`ASSISTANT_TOOLS_SPEC.md`) against the Memory Store.


## Phase 2 — implemented interface locations

Interfaces/stubs only (no DB, no cloud sync, no GitHub commits, no vector runtime, no external provider calls, no UI wiring, no automatic durable writes). New isolated packages:

- `logosforge/memory_arch/` — `schema.py` (MemoryObject, EventLogEntry, enums), `store.py` (`MemoryStore` ABC + `InMemoryMemoryStore`), `policy.py` (`MemoryWriterPolicy`), `retrieval.py`, `contradictions.py`, `sync.py` (disabled), `github_export.py` (disabled).
- `logosforge/assistant_arch/` — `model_gateway.py` (`ProviderCapability`/`ModelRequest`/`ModelResponse`/`ModelProvider`/`ModelGateway` + `DummyModelProvider`), `context_builder.py` (`AssistantContextBuilder`, `ContextBundle`, `MemoryCandidateExtractor`), `orchestration.py` (`AssistantOrchestrator`), `tools.py` (`AssistantTools`).

Tests: `tests/test_memory_architecture_stubs.py` (21). The Alpha assistant (`assistant.py`, Billy/Logos/Dexter) and `providers.py` are unchanged.

**Note:** the Phase-2 `ProviderCapability` in `assistant_arch/model_gateway.py` is the forward-looking abstraction; the live Alpha still uses `logosforge/providers.py`. vLLM remains documented but not yet added to the live `PROVIDER_CAPABILITIES`.


## Phase 5 — Context Builder Retrieval MVP

**Capabilities are consumed, never stored.** `AssistantContextBuilder.build_context(..., provider_id=...)` (`logosforge/assistant_arch/context_builder.py`) reads the selected provider's `ProviderCapability` from the `ModelGateway` and includes a capability snapshot in the `ContextBundle` to inform context-size and tool strategy:

- exposed to the assistant: `provider_id`, `provider_type`, `context_window`, `supports_tools`, `supports_json_schema`, `supports_streaming`, `supports_embeddings`, `supports_vision`, `supports_audio`, `privacy_mode`, `offline_capable`.
- **not** placed in any prompt section: `base_url`, `auth_mode`, or any key/secret.
- if no provider is selected (or it is not registered): an **empty** capability snapshot + a warning, never a crash.

This is the boundary in action: the gateway **reports capabilities**; the context builder **uses them to size/structure context**; neither reads, writes, retrieves, nor persists memory. **No provider is called during context build.** Model backends (LM Studio / Ollama / vLLM / OpenAI / Anthropic / OpenRouter) generate only — they are not LogosForge memory.

Tests: `tests/test_assistant_context_builder.py` (26) — provider inclusion, missing-provider warning, and "no `generate()` call during build" are covered.


## Phase 6 — Passive Assistant Context Integration MVP

When the **default-OFF** flag `assistant_memory_context_enabled` is on, `assistant_arch/passive_context.py` may include a **metadata-only** Provider Capabilities section in the assistant prompt (via the context builder). This changes **nothing** about routing or generation:

- capabilities are read from the `ModelGateway` (or omitted, with a diagnostic warning, if no provider is selected) and serialized as hints (`provider_id`, `provider_type`, `context_window`, `supports_*`, `privacy_mode`, `offline_capable`) — **no `base_url`, no `auth_mode`, no keys**.
- **no provider is called** during prompt build; provider selection, credentials, and `chat_completion` behavior are untouched.
- the gateway still never stores or owns memory — it only reports capabilities, which the prompt builder uses to size/structure context.

Tests: `tests/test_assistant_passive_context_integration.py` (22) — provider-capabilities section presence, and "no sync/GitHub/memory-write during build" are covered.

**Reaffirmed (Phase 6):** model backends (LM Studio / Ollama / vLLM / OpenAI / Anthropic / OpenRouter) are **replaceable generation backends, not memory**; swapping them changes how text is generated, never what LogosForge remembers.
