"""Tests for the Anthropic provider integration."""

import json
import os
from unittest.mock import MagicMock, patch

from logosforge.assistant import (
    _anthropic_completion,
    _openai_completion,
    build_messages,
    chat_completion,
)
from logosforge.providers import (
    PROVIDER_CAPABILITIES,
    PROVIDER_NAMES,
    ProviderConfig,
    default_config,
    get_api_format,
    resolve_api_key,
    validate_provider,
)


# -- Provider registry --------------------------------------------------------

def test_anthropic_in_provider_names():
    assert "Anthropic" in PROVIDER_NAMES


def test_anthropic_capabilities():
    caps = PROVIDER_CAPABILITIES["Anthropic"]
    assert caps.requires_api_key is True
    assert caps.api_format == "anthropic"
    assert caps.supports_model_selection is True
    assert caps.env_key_name == "ANTHROPIC_API_KEY"
    assert "api.anthropic.com" in caps.default_base_url
    assert len(caps.default_models) >= 2


def test_openai_format_default():
    caps = PROVIDER_CAPABILITIES["OpenAI"]
    assert caps.api_format == "openai"


def test_local_providers_have_openai_format():
    for name in ("LM Studio", "Ollama"):
        caps = PROVIDER_CAPABILITIES[name]
        assert caps.api_format == "openai"


def test_default_config_anthropic():
    config = default_config("Anthropic")
    assert config.name == "Anthropic"
    assert "api.anthropic.com" in config.base_url
    assert "claude" in config.model


# -- API format dispatch ------------------------------------------------------

def test_get_api_format_anthropic():
    config = ProviderConfig(name="Anthropic", base_url="https://api.anthropic.com")
    assert get_api_format(config) == "anthropic"


def test_get_api_format_openai():
    config = ProviderConfig(name="OpenAI", base_url="https://api.openai.com/v1")
    assert get_api_format(config) == "openai"


def test_get_api_format_unknown_defaults_openai():
    config = ProviderConfig(name="CustomProvider", base_url="http://example.com")
    assert get_api_format(config) == "openai"


# -- API key resolution -------------------------------------------------------

def test_resolve_api_key_from_config():
    config = ProviderConfig(name="Anthropic", base_url="x", api_key="sk-test")
    assert resolve_api_key(config) == "sk-test"


def test_resolve_api_key_from_env():
    config = ProviderConfig(name="Anthropic", base_url="x", api_key="")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-key"}):
        assert resolve_api_key(config) == "sk-env-key"


def test_resolve_api_key_config_takes_priority():
    config = ProviderConfig(name="Anthropic", base_url="x", api_key="sk-config")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env"}):
        assert resolve_api_key(config) == "sk-config"


def test_resolve_api_key_no_env_returns_empty():
    config = ProviderConfig(name="Anthropic", base_url="x", api_key="")
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert resolve_api_key(config) == ""


def test_resolve_api_key_openai_env():
    config = ProviderConfig(name="OpenAI", base_url="x", api_key="")
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai"}):
        assert resolve_api_key(config) == "sk-openai"


# -- Validation ---------------------------------------------------------------

def test_validate_anthropic_missing_key():
    config = ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_key="",
    )
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        err = validate_provider(config)
        assert err is not None
        assert "API key" in err


def test_validate_anthropic_with_key():
    config = ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_key="sk-test",
    )
    assert validate_provider(config) is None


def test_validate_anthropic_key_from_env():
    config = ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_key="",
    )
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env"}):
        assert validate_provider(config) is None


def test_validate_anthropic_missing_url():
    config = ProviderConfig(
        name="Anthropic",
        base_url="",
        api_key="sk-test",
    )
    err = validate_provider(config)
    assert err is not None
    assert "URL" in err


# -- Request formatting -------------------------------------------------------

def test_anthropic_request_separates_system():
    """Anthropic format places system text at top level, not in messages."""
    messages = build_messages("Rewrite this", "Scene content here.")

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    system_text = messages[0]["content"]
    user_text = messages[1]["content"]

    assert "Scene content here" in user_text
    assert "Rewrite this" in user_text
    assert "writing assistant" in system_text


def test_anthropic_completion_builds_correct_request():
    """Verify the Anthropic request body structure."""
    provider = ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_key="sk-test",
        model="claude-sonnet-4-20250514",
    )

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]

    mock_response = json.dumps({
        "content": [{"type": "text", "text": "Hi there!"}],
        "model": "claude-sonnet-4-20250514",
        "role": "assistant",
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = _anthropic_completion(messages, provider, "sk-test", timeout=30)

    assert result == "Hi there!"

    call_args = mock_open.call_args
    req = call_args[0][0]
    assert req.full_url == "https://api.anthropic.com/v1/messages"
    assert req.get_header("X-api-key") == "sk-test"
    assert req.get_header("Anthropic-version") == "2023-06-01"

    body = json.loads(req.data.decode("utf-8"))
    assert body["system"] == "You are helpful."
    assert body["messages"] == [{"role": "user", "content": "Hello"}]
    assert body["model"] == "claude-sonnet-4-20250514"
    assert body["max_tokens"] == 2048


def test_openai_completion_builds_correct_request():
    """Verify the OpenAI request body structure is unchanged."""
    provider = ProviderConfig(
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="sk-openai",
        model="gpt-4o-mini",
    )

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]

    mock_response = json.dumps({
        "choices": [{"message": {"content": "Hi from OpenAI!"}}],
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = _openai_completion(messages, provider, "sk-openai", timeout=30)

    assert result == "Hi from OpenAI!"

    req = mock_open.call_args[0][0]
    assert "/chat/completions" in req.full_url
    assert req.get_header("Authorization") == "Bearer sk-openai"

    body = json.loads(req.data.decode("utf-8"))
    assert body["messages"] == messages
    assert body["model"] == "gpt-4o-mini"


# -- Dispatch in chat_completion ----------------------------------------------

def test_chat_completion_dispatches_to_anthropic():
    """chat_completion routes to Anthropic format for Anthropic provider."""
    provider = ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_key="sk-test",
        model="claude-sonnet-4-20250514",
    )

    mock_response = json.dumps({
        "content": [{"type": "text", "text": "Anthropic response"}],
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result, cached = chat_completion(
            [{"role": "user", "content": "test"}],
            provider=provider,
            use_cache=False,
        )

    assert result == "Anthropic response"
    assert cached is False


def test_chat_completion_dispatches_to_openai():
    """chat_completion routes to OpenAI format for OpenAI provider."""
    provider = ProviderConfig(
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="sk-openai",
        model="gpt-4o-mini",
    )

    mock_response = json.dumps({
        "choices": [{"message": {"content": "OpenAI response"}}],
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result, cached = chat_completion(
            [{"role": "user", "content": "test"}],
            provider=provider,
            use_cache=False,
        )

    assert result == "OpenAI response"
    assert cached is False


# -- Error handling -----------------------------------------------------------

def test_anthropic_connection_error():
    import urllib.error
    provider = ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_key="sk-test",
        model="claude-sonnet-4-20250514",
    )

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        try:
            chat_completion(
                [{"role": "user", "content": "test"}],
                provider=provider,
                use_cache=False,
            )
            assert False, "Should have raised ConnectionError"
        except ConnectionError as e:
            assert "Anthropic" in str(e)


def test_anthropic_malformed_response():
    provider = ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_key="sk-test",
        model="claude-sonnet-4-20250514",
    )

    mock_response = json.dumps({"error": "bad request"}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        try:
            chat_completion(
                [{"role": "user", "content": "test"}],
                provider=provider,
                use_cache=False,
            )
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Anthropic" in str(e)


# -- Cache works across providers ---------------------------------------------

def test_cache_works_for_anthropic():
    provider = ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_key="sk-test",
        model="claude-sonnet-4-20250514",
    )

    mock_response = json.dumps({
        "content": [{"type": "text", "text": "cached result"}],
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    messages = [{"role": "user", "content": "cache test anthropic"}]

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result1, cached1 = chat_completion(messages, provider=provider, use_cache=True)

    assert result1 == "cached result"
    assert cached1 is False

    result2, cached2 = chat_completion(messages, provider=provider, use_cache=True)
    assert result2 == "cached result"
    assert cached2 is True


# -- Provider switching doesn't break ----------------------------------------

def test_all_providers_have_required_fields():
    for name, caps in PROVIDER_CAPABILITIES.items():
        assert hasattr(caps, "api_format"), f"{name} missing api_format"
        assert caps.api_format in ("openai", "anthropic"), f"{name} bad api_format"
        assert isinstance(caps.default_models, list)
        assert isinstance(caps.default_base_url, str)
        assert len(caps.default_base_url) > 0


# -- UI: ProviderSettingsWidget -----------------------------------------------

def test_provider_widget_includes_anthropic():
    from logosforge.ui.provider_settings import ProviderSettingsWidget
    widget = ProviderSettingsWidget(compact=True)
    combo = widget._provider_combo
    items = [combo.itemText(i) for i in range(combo.count())]
    assert "Anthropic" in items


def test_provider_widget_anthropic_shows_key_field():
    from logosforge.ui.provider_settings import ProviderSettingsWidget
    widget = ProviderSettingsWidget(compact=True)
    idx = widget._provider_combo.findText("Anthropic")
    widget._provider_combo.setCurrentIndex(idx)
    assert not widget._key_input.isHidden()


def test_provider_widget_anthropic_shows_models():
    from logosforge.ui.provider_settings import ProviderSettingsWidget
    widget = ProviderSettingsWidget(compact=True)
    idx = widget._provider_combo.findText("Anthropic")
    widget._provider_combo.setCurrentIndex(idx)
    model_count = widget._model_combo.count()
    assert model_count >= 2
    items = [widget._model_combo.itemText(i) for i in range(model_count)]
    assert any("claude" in m for m in items)


def test_provider_widget_switch_providers():
    from logosforge.ui.provider_settings import ProviderSettingsWidget
    widget = ProviderSettingsWidget(compact=True)

    for name in PROVIDER_NAMES:
        idx = widget._provider_combo.findText(name)
        widget._provider_combo.setCurrentIndex(idx)
        config = widget.get_provider_config()
        assert config.name == name
        assert config.base_url != ""
