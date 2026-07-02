"""LLM provider configuration and capabilities for the writing assistant."""

import os
from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str = ""
    model: str = ""
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ProviderCapabilities:
    requires_api_key: bool
    default_base_url: str
    supports_local: bool
    default_models: list[str]
    supports_model_selection: bool
    extra_headers: dict[str, str] = field(default_factory=dict)
    api_format: str = "openai"
    env_key_name: str = ""


PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "LM Studio": ProviderCapabilities(
        requires_api_key=False,
        default_base_url="http://localhost:1234/v1",
        supports_local=True,
        default_models=[],
        supports_model_selection=False,
    ),
    "Ollama": ProviderCapabilities(
        requires_api_key=False,
        default_base_url="http://localhost:11434/v1",
        supports_local=True,
        default_models=[
            "llama3.3",
            "llama3.2",
            "llama3.1",
            "llama3",
            "mistral",
            "mixtral",
            "qwen3",
            "qwen2.5",
            "gemma3",
            "gemma2",
            "phi4",
            "phi3",
            "deepseek-r1",
            "deepseek-v3",
            "command-r",
            "codellama",
            "llava",
        ],
        supports_model_selection=True,
    ),
    "OpenAI": ProviderCapabilities(
        requires_api_key=True,
        default_base_url="https://api.openai.com/v1",
        supports_local=False,
        default_models=[
            "o3",
            "o3-pro",
            "o4-mini",
            "o3-mini",
            "o1",
            "o1-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "chatgpt-4o-latest",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
        ],
        supports_model_selection=True,
        env_key_name="OPENAI_API_KEY",
    ),
    "Anthropic": ProviderCapabilities(
        requires_api_key=True,
        default_base_url="https://api.anthropic.com",
        supports_local=False,
        default_models=[
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ],
        supports_model_selection=True,
        api_format="anthropic",
        env_key_name="ANTHROPIC_API_KEY",
    ),
    "OpenRouter": ProviderCapabilities(
        requires_api_key=True,
        default_base_url="https://openrouter.ai/api/v1",
        supports_local=False,
        default_models=[
            "openrouter/auto",
            "anthropic/claude-opus-4-8",
            "anthropic/claude-opus-4-7",
            "anthropic/claude-sonnet-4-6",
            "anthropic/claude-opus-4-6",
            "anthropic/claude-haiku-4.5",
            "openai/o3",
            "openai/o3-pro",
            "openai/o4-mini",
            "openai/gpt-4.1",
            "openai/gpt-4.1-mini",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "google/gemini-2.5-pro",
            "google/gemini-2.5-flash",
            "google/gemini-2.0-flash",
            "meta-llama/llama-3.3-70b-instruct",
            "meta-llama/llama-3.1-405b-instruct",
            "deepseek/deepseek-r1",
            "deepseek/deepseek-chat-v3",
            "mistralai/mistral-large",
            "mistralai/mistral-small",
            "qwen/qwen-2.5-72b-instruct",
        ],
        supports_model_selection=True,
        extra_headers={"HTTP-Referer": "logosforge-app"},
        env_key_name="OPENROUTER_API_KEY",
    ),
}

PROVIDER_NAMES = list(PROVIDER_CAPABILITIES.keys())


def default_config(name: str) -> ProviderConfig:
    caps = PROVIDER_CAPABILITIES[name]
    return ProviderConfig(
        name=name,
        base_url=caps.default_base_url,
        model=caps.default_models[0] if caps.default_models else "",
        extra_headers=dict(caps.extra_headers),
    )


# Default endpoint used when nothing is configured (matches the prior wrappers).
_DEFAULT_LOCAL_BASE_URL = "http://localhost:1234/v1"


def build_active_provider(*, require_configured: bool = False) -> "ProviderConfig | None":
    """Resolve the single, currently-configured AI provider from settings.

    This is the one place every feature builds its provider from — it reads the
    same four settings keys (``ai_provider`` / ``ai_base_url`` / ``ai_model`` /
    ``ai_api_key``) the Assistant settings UI writes, so provider switching,
    per-provider memory and autosave all flow through unchanged.

    * ``require_configured=False`` (default): always returns a config, falling
      back to ``LM Studio`` at the local endpoint when nothing is set. (Matches
      the background-feature wrappers that assume a local server.)
    * ``require_configured=True``: returns ``None`` when neither a provider name
      nor a base URL is set. (Matches the UI wrappers that must not call an
      unconfigured provider.)

    Never logs the API key; never mutates settings.
    """
    from logosforge.settings import get_manager

    mgr = get_manager()
    name = str(mgr.get("ai_provider") or "")
    base_url = str(mgr.get("ai_base_url") or "")
    if require_configured and not (name or base_url):
        return None
    return ProviderConfig(
        name=name or "LM Studio",
        base_url=base_url or _DEFAULT_LOCAL_BASE_URL,
        model=str(mgr.get("ai_model") or ""),
        api_key=str(mgr.get("ai_api_key") or ""),
    )


def resolve_api_key(config: ProviderConfig) -> str:
    """Return the API key from config, falling back to environment variable."""
    if config.api_key:
        return config.api_key
    caps = PROVIDER_CAPABILITIES.get(config.name)
    if caps and caps.env_key_name:
        return os.environ.get(caps.env_key_name, "")
    return ""


def get_api_format(config: ProviderConfig) -> str:
    caps = PROVIDER_CAPABILITIES.get(config.name)
    return caps.api_format if caps else "openai"


def validate_provider(config: ProviderConfig) -> str | None:
    """Return an error message, or None if config is valid."""
    caps = PROVIDER_CAPABILITIES.get(config.name)
    if caps is None:
        return f"Unknown provider: {config.name}"
    if not config.base_url:
        return "Base URL is required."
    if caps.requires_api_key and not resolve_api_key(config):
        return f"{config.name} requires an API key."
    return None
